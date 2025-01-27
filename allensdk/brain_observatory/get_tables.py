#%%
import os
import pandas as pd
from tqdm import tqdm
from allensdk.brain_observatory.behavior.behavior_project_cache.project_apis\
    .data_io import \
    BehaviorProjectLimsApi
from allensdk.brain_observatory.behavior.data_files import BehaviorStimulusFile
from allensdk.brain_observatory.behavior.data_objects import BehaviorSessionId
from allensdk.internal.api import db_connection_creator
from allensdk.core.auth_config import LIMS_DB_CREDENTIAL_MAP
from allensdk.brain_observatory.behavior.data_objects.metadata.subject_metadata.subject_metadata import SubjectMetadata
#%%


def get_all_tables(project_code: str):
    lims_db = db_connection_creator(fallback_credentials=LIMS_DB_CREDENTIAL_MAP)
    api = BehaviorProjectLimsApi.default(passed_only=False)
    session_table = api.get_ophys_session_table().reset_index()
    session_df = session_table[session_table.project_code==project_code].reset_index(drop=True)
    behavior_session_ids = session_df['behavior_session_id'].values
    main_paths = []
    session_types = []
    mouse_ids = []
    cre_lines = []
    full_genotypes = []
    reporter_lines = []
    desc = 'loading stimulus pkl files'

    for i_session in tqdm (range(len(behavior_session_ids)), desc=desc):
        ophys_experiment_id = session_df['ophys_experiment_id'][i_session][0]
        behavior_session_id = BehaviorSessionId.from_lims(
            ophys_experiment_id=ophys_experiment_id, db=lims_db)
        subject_metadata = SubjectMetadata.from_lims(
            behavior_session_id=behavior_session_id,lims_db=lims_db)
        
        stimulus_file = BehaviorStimulusFile.from_lims(
                    db=lims_db, behavior_session_id=behavior_session_id.value)
        session_types.append(stimulus_file.session_type)
        main_paths.append(os.sep.join(stimulus_file.filepath.split(os.sep)[:-3]))
        mouse_ids.append(int(subject_metadata.mouse_id))
        cre_lines.append(subject_metadata.cre_line)
        full_genotypes.append(subject_metadata.full_genotype)
        reporter_lines.append(subject_metadata.reporter_line)

    session_df['main_path'] = main_paths
    session_df['session_type'] = session_types   
    session_df['mouse_id'] = mouse_ids 
    session_df['cre_line'] = cre_lines
    session_df['full_genotype'] = full_genotypes
    session_df['reporter_line'] = reporter_lines  

    experiments_table = api.get_ophys_experiment_table().reset_index()
    experiments_df = experiments_table[experiments_table.project_code==project_code].reset_index(drop=True)
    experiments_df = experiments_df.merge(session_df.drop(columns=['ophys_experiment_id','ophys_container_id','session_name','date_of_acquisition','project_code','ophys_session_id']), on='behavior_session_id')

    cells_df = api.get_ophys_cells_table().reset_index()
    cells_df = cells_df.merge(experiments_df, on='ophys_experiment_id')

    return (session_df, experiments_df, cells_df)


def get_session_table(project_code: str):
    lims_db = db_connection_creator(fallback_credentials=LIMS_DB_CREDENTIAL_MAP)
    api = BehaviorProjectLimsApi.default(passed_only=False)
    session_table = api.get_ophys_session_table().reset_index()
    session_df = session_table[session_table.project_code==project_code].reset_index(drop=True)
    behavior_session_ids = session_df['behavior_session_id'].values
    main_paths = []
    session_types = []
    mouse_ids = []
    desc = 'loading stimulus pkl files'
    for i_session in tqdm (range(len(behavior_session_ids)), desc=desc):
        behavior_session_id = behavior_session_ids[i_session]
        stimulus_file = BehaviorStimulusFile.from_lims(
                    db=lims_db, behavior_session_id=behavior_session_id)\
                    .validate()
        main_paths.append(os.sep.join(stimulus_file.filepath.split(os.sep)[:-3]))
        session_types.append(stimulus_file.session_type)
        try:
            mouse_ids.append(stimulus_file.data['items']['behavior']['params']['mouse_id'])
        except:
            mouse_ids.append(stimulus_file.data['mouse_id'])

    session_df['main_path'] = main_paths
    session_df['session_type'] = session_types   
    session_df['mouse_id'] = mouse_ids   

    return session_df

def get_experiment_table(project_code: str):
    session_df = get_session_table(project_code = project_code)
    api = BehaviorProjectLimsApi.default(passed_only=False)
    experiments_table = api.get_ophys_experiment_table().reset_index()
    experiments_df = experiments_table[experiments_table.project_code==project_code].reset_index(drop=True)
    experiments_df = experiments_df.merge(session_df.drop(columns=['ophys_experiment_id','ophys_container_id','session_name','date_of_acquisition','project_code','ophys_session_id']), on='behavior_session_id')

    return experiments_df

def get_cell_table(project_code: str):
    experiments_df = get_experiment_table(project_code = project_code)
    api = BehaviorProjectLimsApi.default(passed_only=False)
    cells_df = api.get_ophys_cells_table().reset_index()
    cells_df = cells_df.merge(experiments_df, on='ophys_experiment_id')

    return cells_df



