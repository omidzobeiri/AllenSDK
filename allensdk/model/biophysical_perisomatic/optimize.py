from allensdk.model.biophys_sim.config import Config
from allensdk.model.biophysical_perisomatic.deap_utils import Utils
import neuron_parallel

import argparse

import numpy as np
import random

from deap import algorithms
from deap import base
from deap import creator
from deap import tools

BOUND_LOWER, BOUND_UPPER = 0.0, 1.0

utils = None
h = None
do_block_check = None
t_vec = None
v_ved = None
i_vec = None

def eval_param_set(params):
    utils.set_normalized_parameters(params)
    h.finitialize()
    h.run()
    feature_errors = utils.calculate_feature_errors(t_vec.as_numpy(), v_vec.as_numpy(), i_vec.as_numpy())
    min_fail_penalty = 75.0
    if do_block_check and np.sum(feature_errors) < min_fail_penalty * len(feature_errors):
        if check_for_block():
            feature_errors = min_fail_penalty * np.ones_like(feature_errors)
        # Reset the stimulus back
        utils.set_iclamp_params(stim_params["amplitude"], stim_params["delay"],
            stim_params["duration"])

    return [np.sum(feature_errors)]

def check_for_block():
    utils.set_iclamp_params(max_stim_amp, stim_params["delay"],
        stim_params["duration"])
    h.finitialize()
    h.run()

    v = v_vec.as_numpy()
    t = t_vec.as_numpy()
    stim_start_idx = np.flatnonzero(t >= utils.stim.delay)[0]
    stim_end_idx = np.flatnonzero(t >= utils.stim.delay + utils.stim.dur)[0]
    depol_block_threshold = -50.0 # mV
    block_min_duration = 50.0 # ms
    long_hyperpol_threshold = -75.0 # mV

    bool_v = np.array(v > depol_block_threshold, dtype=int)
    up_indexes = np.flatnonzero(np.diff(bool_v) == 1)
    down_indexes = np.flatnonzero(np.diff(bool_v) == -1)
    if len(up_indexes) > len(down_indexes):
        down_indexes = np.append(down_indexes, [stim_end_idx])

    if len(up_indexes) == 0:
        # if it never gets high enough, that's not a good sign (meaning no spikes)
        return True
    else:
        max_depol_duration = np.max([t[down_indexes[k]] - t[up_idx] for k, up_idx in enumerate(up_indexes)])
        if max_depol_duration > block_min_duration:
            return True

    bool_v = np.array(v > long_hyperpol_threshold, dtype=int)
    up_indexes = np.flatnonzero(np.diff(bool_v) == 1)
    down_indexes = np.flatnonzero(np.diff(bool_v) == -1)
    down_indexes = down_indexes[(down_indexes > stim_start_idx) & (down_indexes < stim_end_idx)]
    if len(down_indexes) != 0:
        up_indexes = up_indexes[(up_indexes > stim_start_idx) & (up_indexes < stim_end_idx) & (up_indexes > down_indexes[0])]
        if len(up_indexes) < len(down_indexes):
            up_indexes = np.append(up_indexes, [stim_end_idx])
        max_hyperpol_duration = np.max([t[up_indexes[k]] - t[down_idx] for k, down_idx in enumerate(down_indexes)])
        if max_hyperpol_duration > block_min_duration:
            return True
    return False

def uniform(lower, upper, size=None):
    if size is None:
        return [random.uniform(a, b) for a, b in zip(lower, upper)]
    else:
        return [random.uniform(a, b) for a, b in zip([lower] * size, [upper] * size)]

def best_sum(d):
    return np.sum(d, axis=1).min()

def initPopulation(pcls, ind_init, popfile):
    popdata = np.loadtxt(popfile)
    return pcls(ind_init(utils.normalize_actual_parameters(line)) for line in popdata.tolist())


def main():
    global utils, h, v_vec, i_vec, t_vec, do_block_check, max_stim_amp, max_stim_params
    parser = argparse.ArgumentParser(description='Start a DEAP testing run.')
    parser.add_argument('seed', type=int)
    parser.add_argument('config_path')
    args = parser.parse_args()
    seed = args.seed

    # Set up NEURON
    config = Config().load(args.config_path)
    stim_params = config.data["stimulus"][0]

    block_check_fit_types = ["f9", "f13"]
    do_block_check = False
    if config.data["fit_name"] in block_check_fit_types:
        max_stim_amp = config.data["fitting"][0]["max_stim_test_na"]
        if max_stim_amp > stim_params["amplitude"]:
            print "Will check for blocks"
            do_block_check = True

    utils = Utils(config)
    h = utils.h

    manifest = config.manifest
    morphology_path = manifest.get_path('MORPHOLOGY')
    utils.generate_morphology(morphology_path.encode('ascii', 'ignore'))
    utils.load_cell_parameters()
    utils.insert_iclamp()
    utils.set_iclamp_params(stim_params["amplitude"], stim_params["delay"],
        stim_params["duration"])

    h.tstop = stim_params["delay"] * 2.0 + stim_params["duration"]
    h.cvode_active(1)
    h.cvode.atolscale("cai", 1e-4)
    h.cvode.maxstep(10)

    v_vec, i_vec, t_vec = utils.record_values()

    neuron_parallel.runworker()

    # Set up genetic algorithm

    print "Setting up GA"
    random.seed(seed)

    ngen = 500 
    mu = 1200
    cxpb = 0.1
    mtpb = 0.35
    eta = 10.0

    ndim = len(config.data["channels"]) + len(config.data["addl_params"])

    creator.create("FitnessMin", base.Fitness, weights=(-1.0, ))
    creator.create("Individual", list, fitness=creator.FitnessMin)

    toolbox = base.Toolbox()

    toolbox.register("attr_float", uniform, BOUND_LOWER, BOUND_UPPER, ndim)
    toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.attr_float)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    toolbox.register("evaluate", eval_param_set)
    toolbox.register("mate", tools.cxSimulatedBinaryBounded, low=BOUND_LOWER, up=BOUND_UPPER,
        eta=eta)
    toolbox.register("mutate", tools.mutPolynomialBounded, low=BOUND_LOWER, up=BOUND_UPPER,
        eta=eta, indpb=mtpb)
    toolbox.register("variate", algorithms.varAnd)
    toolbox.register("select", tools.selBest)
    toolbox.register("map", neuron_parallel.map)

    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("min", np.min, axis=0)
    stats.register("max", np.max, axis=0)
    stats.register("best", best_sum)

    logbook = tools.Logbook()
    logbook.header = "gen", "nevals", "min", "max", "best"

    if "STARTPOP" in manifest.path_info:
        print "Using a pre-defined starting population"
        start_pop_path = config.manifest.get_path("STARTPOP")
        toolbox.register("population_start", initPopulation, list, creator.Individual)
        pop = toolbox.population_start(start_pop_path)
    else:
        pop = toolbox.population(n=mu)

    invalid_ind = [ind for ind in pop if not ind.fitness.valid]
    fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)

    for ind, fit in zip(invalid_ind, fitnesses):
        ind.fitness.values = fit

    hof = tools.HallOfFame(mu)
    hof.update(pop)

    record = stats.compile(pop)
    logbook.record(gen=0, nevals=len(invalid_ind), **record)
    print logbook.stream

    for gen in range(1, ngen + 1):
        offspring = toolbox.variate(pop, toolbox, cxpb, 1.0)

        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit

        hof.update(offspring)

        pop[:] = toolbox.select(pop + offspring, mu)

        record = stats.compile(pop)
        logbook.record(gen=gen, nevals=len(invalid_ind), **record)
        print logbook.stream

    fit_dir = config.manifest.get_path("FITDIR")
    seed_dir = fit_dir + "/s{:d}/".format(seed)
    np.savetxt(seed_dir + "final_pop.txt", np.array(map(utils.actual_parameters_from_normalized, pop)))
    np.savetxt(seed_dir + "final_pop_fit.txt", np.array([ind.fitness.values for ind in pop]))
    np.savetxt(seed_dir + "final_hof.txt", np.array(map(utils.actual_parameters_from_normalized, hof)))
    np.savetxt(seed_dir + "final_hof_fit.txt", np.array([ind.fitness.values for ind in hof]))
    neuron_parallel.done()
    h.quit()

if __name__ == "__main__":
    main()