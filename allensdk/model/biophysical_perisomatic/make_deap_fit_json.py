import argparse
import os.path
import numpy as np
import json
from allensdk.core.nwb_data_set import NwbDataSet
import allensdk.model.biophysical_perisomatic.fits.fit_styles
from pkg_resources import resource_filename #@UnresolvedImport
from allensdk.model.biophys_sim.config import DescriptionParser
from allensdk.model.biophysical_perisomatic import ephys_utils


class Report:

    def __init__(self,
                 description,
                 fit_type,
                 manifest_file_name='optimize_manifest_local.json'):
        self.description = description
        self.manifest = self.description.manifest
        self.specimen_id = str(description.data['runs'][0]['specimen_id'])
        self.fit_type = fit_type
        self.fit_directory = self.manifest.get_path('WORKDIR')
        self.target_path = self.manifest.get_path('target_path')
    
        with open(self.target_path, "r") as f:
            self.target = json.load(f)  # TODO: replace this w/ json utils
    
        self.seeds = [1234, 1001, 4321, 1024, 2048]
        self.org_selections = [0, 100, 500, 1000] # Picks thek best, 100th best, etc. organisms as examples
        self.trace_colors = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a"]
        
        self.config_path = self.manifest.get_path('fit_config_json',
                                                   self.fit_type)
         
        with open(self.config_path, "r") as f:
            self.fit_config = json.load(f)     # TODO: replace this w/ json utils
        
        fit_style_json = os.path.basename(self.fit_config["biophys"][0]["model_file"][-1])
        
        fit_style_path = \
            resource_filename(allensdk.model.biophysical_perisomatic.fits.fit_styles.__name__,
                              fit_style_json)
        
        with open(fit_style_path, "r") as f:
            self.fit_style_info = json.load(f)
        self.used_features = self.fit_style_info["features"]
        self.all_params = self.fit_style_info["channels"] + self.fit_style_info["addl_params"]
        
        nwb_path = self.manifest.get_path('output')
        self.data_set = NwbDataSet(nwb_path)
    
    
    def best_fit_value(self):
        return self.all_hof_fit_errors[self.sorted_indexes[self.org_selections[0]]]
    
    
    def generate_fit_file(self):
        self.gather_from_seeds()
        self.make_fit_json_file()
    
    
    def make_fit_json_file(self):
        json_data = {}
        
        # passive
        json_data["passive"] = [{}]
        json_data["passive"][0]["ra"] = self.target["passive"][0]["ra"]
        json_data["passive"][0]["e_pas"] = self.target["passive"][0]["e_pas"]
        json_data["passive"][0]["cm"] = []
        for k in self.target["passive"][0]["cm"]:
            json_data["passive"][0]["cm"].append({"section": k, "cm": self.target["passive"][0]["cm"][k]})
        
        # fitting
        json_data["fitting"] = [{}]
        json_data["fitting"][0]["sweeps"] = self.target["fitting"][0]["sweeps"]
        json_data["fitting"][0]["junction_potential"] = self.target["fitting"][0]["junction_potential"]
        
        # conditions
        json_data["conditions"] = self.fit_style_info["conditions"]
        json_data["conditions"][0]["v_init"] = self.target["passive"][0]["e_pas"]
        
        # genome
        json_data["genome"] = []
        genome_vals = self.all_hof_fits[self.sorted_indexes[self.org_selections[0]], :]
        for i, p in enumerate(self.all_params):
            if len(p["mechanism"]) > 0:
                param_name = p["parameter"] + "_" + p["mechanism"]
            else:
                param_name = p["parameter"]
            json_data["genome"].append({"value": genome_vals[i],
                                        "section": p["section"],
                                        "name": param_name,
                                        "mechanism": p["mechanism"]
                                        })
        
        # write out file
        with open(self.manifest.get_path('output_fit_file',
                                         self.specimen_id,
                                         self.fit_type), "w") as f:
            json.dump(json_data, f, indent=2)


    def gather_from_seeds(self):
        first_created = False
        for s in self.seeds:
            final_hof_fit_path = self.manifest.get_path('final_hof_fit',
                                                        self.fit_type,
                                                        s)
            final_hof_path = self.manifest.get_path('final_hof',
                                                    self.fit_type,
                                                    s)
            if not os.path.exists(final_hof_fit_path):
                print "Could not find output file for seed {:d}".format(s)
                continue
            hof_fit_errors = np.loadtxt(final_hof_fit_path)
            hof_fits = np.loadtxt(final_hof_path)
            if not first_created:
                all_hof_fit_errors = hof_fit_errors.copy()
                all_hof_fits = hof_fits.copy()
                first_created = True
            else:
                all_hof_fit_errors = np.hstack([all_hof_fit_errors, hof_fit_errors])
                all_hof_fits = np.vstack([all_hof_fits, hof_fits])
        self.all_hof_fits = all_hof_fits
        self.all_hof_fit_errors = all_hof_fit_errors
        self.sorted_indexes = np.argsort(self.all_hof_fit_errors)

    
    def check_org_selections_for_noise_block(self):
        h = self.utils.h
        v_vec, i_vec, t_vec = self.utils.record_values()

        depol_block_threshold = -50.0 # mV
        block_min_duration = 50.0 # ms

        h.cvode_active(0)
        noise_i_stim = []
        for sweep_type in ["C1NSSEED_1", "C1NSSEED_2"]:
            sweeps = ephys_utils.get_sweeps_of_type(sweep_type, self.specimen_id)
            _, expt_i, expt_t = ephys_utils.get_sweep_v_i_t_from_set(self.data_set, sweeps[0])
            noise_i_stim.append(expt_i)
        dt = (expt_t[1] - expt_t[0]) * 1e3
        h.dt = dt
        h.tstop = expt_t[-1] * 1e3
        self.utils.stim.dur = 1e12

        for ii, org_ind in enumerate(self.sorted_indexes):
            print "Testing org ", ii, org_ind
            self.utils.set_actual_parameters(self.all_hof_fits[org_ind, :])
            depol_okay = True
            use_ii = -1
            for expt_i in noise_i_stim:
                print "Running some noise"
                i_stim_vec = h.Vector(expt_i * 1e-3)
                i_stim_vec.play(self.utils.stim._ref_amp, dt)
                h.finitialize()
                h.run()
                i_stim_vec.play_remove()

                v = v_vec.as_numpy()
                t = t_vec.as_numpy()
                i = i_vec.as_numpy()
                stim_start_idx = 0
                stim_end_idx = len(t) - 1
                bool_v = np.array(v > depol_block_threshold, dtype=int)
                up_indexes = np.flatnonzero(np.diff(bool_v) == 1)
                down_indexes = np.flatnonzero(np.diff(bool_v) == -1)
                if len(up_indexes) > len(down_indexes):
                    down_indexes = np.append(down_indexes, [stim_end_idx])

                if len(up_indexes) != 0:
                    max_depol_duration = np.max([t[down_indexes[k]] - t[up_idx] for k, up_idx in enumerate(up_indexes)])
                    if max_depol_duration > block_min_duration:
                        print "Encountered depolarization block"
                        depol_okay = False
#                         plt.figure()
#                         plt.plot(t, v)
#                         plt.show(block=True)
                        break
            if depol_okay:
                print "Did not detect depolarization block on noise traces"
                use_ii = ii
                break
        h.cvode_active(1)
        self.utils.set_iclamp_params(self.stim_params["amplitude"], self.stim_params["delay"],
            self.stim_params["duration"])
        self.utils.h.tstop = self.stim_params["delay"] * 2.0 + self.stim_params["duration"]

        if use_ii == -1:
            print "Could not find an organism without depolarization block on noise."
        else:
            self.org_selections = [o + use_ii for o in self.org_selections]



def main(description_path):
    fit_types = ["f9", "f13"]
    
    reader = DescriptionParser()
    description = reader.read(description_path)
    
    for fit_type in fit_types:
        fit_type_dir = description.manifest.get_path('fit_type_path', fit_type)
        
        if os.path.exists(fit_type_dir):
            report = Report(description,
                            fit_type)
            
            report.generate_fit_file()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='generate report on DEAP optimization run')
    parser.add_argument('manifest_json')
    args = parser.parse_args()
#    sns.set_style("white")

    main(args.manifest_json)


