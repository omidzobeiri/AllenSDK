import pytest
import pandas as pd
import numpy as np

from .conftest import MockSessionApi
from allensdk.brain_observatory.ecephys.ecephys_session import EcephysSession
from allensdk.brain_observatory.ecephys.stimulus_analysis.receptive_field_mapping import ReceptiveFieldMapping, rf_stats

class MockRFMSessionApi(MockSessionApi):
    def get_stimulus_presentations(self):
        features = np.array(np.meshgrid([30.0, -20.0, 40.0, 20.0, 0.0, -30.0, -40.0, 10.0, -10.0],  # x_position
                                        [10.0, -10.0, 30.0, 40.0, -40.0, -30.0, -20.0, 20.0, 0.0])  # y_position
                            ).reshape(2, 81)

        return pd.DataFrame({
            'start_time': np.concatenate(([0.0], np.linspace(0.5, 20.50, 81, endpoint=True), [20.75])),
            'stop_time': np.concatenate(([0.5], np.linspace(0.75, 20.75, 81, endpoint=True), [21.25])),
            'stimulus_name': ['spontaneous'] + ['gabors']*81 + ['spontaneous'],
            'stimulus_block': [0] + [1]*81 + [0],
            'duration': [0.5] + [0.25]*81 + [0.5],
            'stimulus_index': [0] + [1]*81 + [0],
            'x_position': np.concatenate(([np.nan], features[0, :], [np.nan])),
            'y_position': np.concatenate(([np.nan], features[1, :], [np.nan]))
        }, index=pd.Index(name='id', data=np.arange(83)))


@pytest.fixture
def ecephys_api():
    return MockRFMSessionApi()


def mock_ecephys_api():
    return MockRFMSessionApi()


def test_load(ecephys_api):
    session = EcephysSession(api=ecephys_api)
    rfm = ReceptiveFieldMapping(ecephys_session=session)
    assert(rfm.name == 'Receptive Field Mapping')
    assert(set(rfm.unit_ids) == set(range(6)))
    assert(len(rfm.conditionwise_statistics) == 81*6)
    assert(rfm.conditionwise_psth.shape == (81, 249, 6))
    assert(not rfm.presentationwise_spike_times.empty)
    assert(len(rfm.presentationwise_statistics) == 81*6)
    assert(len(rfm.stimulus_conditions) == 81)


def test_stimulus(ecephys_api):
    session = EcephysSession(api=ecephys_api)
    rfm = ReceptiveFieldMapping(ecephys_session=session)
    assert(isinstance(rfm.stim_table, pd.DataFrame))
    assert(len(rfm.stim_table) == 81)
    assert(set(rfm.stim_table.columns).issuperset({'x_position', 'y_position', 'start_time', 'stop_time'}))

    assert(set(rfm.azimuths) == {30.0, -20.0, 40.0, 20.0, 0.0, -30.0, -40.0, 10.0, -10.0})
    assert(rfm.number_azimuths == 9)

    assert(set(rfm.elevations) == {10.0, -10.0, 30.0, 40.0, -40.0, -30.0, -20.0, 20.0, 0.0})
    assert(rfm.number_elevations == 9)


def test_metrics():
    session = EcephysSession(api=mock_ecephys_api())
    rfm = ReceptiveFieldMapping(ecephys_session=session)
    assert(isinstance(rfm.metrics, pd.DataFrame))
    assert(len(rfm.metrics) == 6)
    assert(rfm.metrics.index.names == ['unit_id'])

    assert('azimuth_rf' in rfm.metrics.columns)
    assert('elevation_rf' in rfm.metrics.columns)
    assert('width_rf' in rfm.metrics.columns)
    assert('height_rf' in rfm.metrics.columns)
    assert('area_rf' in rfm.metrics.columns)
    assert('p_value_rf' in rfm.metrics.columns)
    assert('on_screen_rf' in rfm.metrics.columns)
    assert('firing_rate_rf' in rfm.metrics.columns)
    assert('fano_rf' in rfm.metrics.columns)
    assert('time_to_peak_rf' in rfm.metrics.columns)
    assert('reliability_rf' in rfm.metrics.columns)
    assert('lifetime_sparseness_rf' in rfm.metrics.columns)
    assert('run_pval_rf' in rfm.metrics.columns)
    assert('run_mod_rf' in rfm.metrics.columns)


# Some special receptive fields for testing
rf_field_real = np.array([[7440, 5704,  11408, 8184, 9920, 5952, 11904, 11904, 9672],
                          [8184, 12152, 10912, 12648, 15128, 19096, 17112, 14384, 11656],
                          [12152, 17856, 25048, 36208, 47368, 30256, 20336, 10912, 10168],
                          [15624, 31000, 53568, 92752, 119288, 69440, 31496, 16120, 10416],
                          [12152, 23560, 32984, 74896, 93496, 52328, 28024, 19592, 11656],
                          [9672, 7192, 10912, 16120, 16368, 18600, 14880, 6696, 11408],
                          [11656, 7688, 6696, 5456, 11408, 9672, 11160, 12152, 7936],
                          [6696, 6696, 9424, 8928, 6200, 11160, 7688, 6200, 9672],
                          [8928, 10912, 9176, 8432, 7688, 9424, 5704, 8184, 14384]])

x, y = np.meshgrid(np.linspace(-1, 1, 9), np.linspace(-1, 1, 9))
rf_field_gaussian = np.exp(-((np.sqrt(x*x + y*y) - 0.0)**2 /(2.0*1.0**2)))

rf_field_edge = np.zeros((9, 9))
rf_field_edge[8, 8] = 5.0


@pytest.mark.parametrize('rf_field,threshold,expected',
                         [
                             (rf_field_real, 0.5, (3.5, 3.0, 1.044852108639198, 1.6647756938016467, 2.0, True)),
                             (rf_field_gaussian, 0.5, (4.0, 4.0, 4.0, 3.9999999999999996, 9.0, True)),
                             (np.full((9, 9), 5.2), 0.5, (np.nan, np.nan, 95084.02571548845, 98101.06119970477, 0.0, True)),
                             (np.zeros((9, 9)), 0.5, (np.nan, np.nan, np.nan, np.nan, np.nan, False)),
                             (rf_field_edge, 0.5, (8.0, 8.0, 0.0, 0.0, 1.0, True))
                         ])
def test_rf_stats(rf_field, threshold, expected):
    stats = rf_stats(rf_field, threshold)
    assert(np.allclose(stats, expected, equal_nan=True))



@pytest.mark.skip(reason='Write a test for the receptive_fields()/_get_rf() methods')
def test_receptive_fields():
    # TODO: Implement
    pass


@pytest.mark.skip()
def test_response_by_stimulus_position():
    # TODO: Implement
    pass


if __name__ == '__main__':
    # test_load()
    # test_stimulus()
    test_metrics()
