from typing import Optional

import numpy as np
from pynwb import NWBFile, ProcessingModule
from pynwb.base import TimeSeries

from allensdk.core import \
    LimsReadableInterface, NwbReadableInterface
from allensdk.brain_observatory.behavior.data_files.sync_file import \
    SyncFileReadableInterface
from allensdk.brain_observatory.behavior.data_files.stimulus_file import \
    StimulusFileReadableInterface
from allensdk.core import DataObject
from allensdk.brain_observatory.behavior.data_files import (
    BehaviorStimulusFile, SyncFile
)
from allensdk.core import NwbWritableInterface
from allensdk.brain_observatory.behavior.data_objects.timestamps\
    .stimulus_timestamps.timestamps_processing import (
        get_behavior_stimulus_timestamps, get_ophys_stimulus_timestamps)
from allensdk.internal.api import PostgresQueryMixin


class StimulusTimestamps(DataObject,
                         StimulusFileReadableInterface,
                         SyncFileReadableInterface,
                         NwbReadableInterface,
                         LimsReadableInterface,
                         NwbWritableInterface,):
    """A DataObject which contains properties and methods to load, process,
    and represent visual behavior stimulus timestamp data.

    Stimulus timestamp data is represented as:

    Numpy array whose length is equal to the number of timestamps collected
    and whose values are timestamps (in seconds)
    """

    def __init__(
        self,
        timestamps: np.ndarray,
        monitor_delay: float,
        stimulus_file: Optional[BehaviorStimulusFile] = None,
        sync_file: Optional[SyncFile] = None
    ):
        super().__init__(name="stimulus_timestamps",
                         value=timestamps+monitor_delay)
        self._stimulus_file = stimulus_file
        self._sync_file = sync_file
        self._monitor_delay = monitor_delay

    @classmethod
    def from_stimulus_file(
            cls,
            stimulus_file: BehaviorStimulusFile,
            monitor_delay: float) -> "StimulusTimestamps":
        stimulus_timestamps = get_behavior_stimulus_timestamps(
            stimulus_pkl=stimulus_file.data
        )

        return cls(
            timestamps=stimulus_timestamps,
            monitor_delay=monitor_delay,
            stimulus_file=stimulus_file
        )

    @classmethod
    def from_sync_file(
            cls,
            sync_file: SyncFile,
            monitor_delay: float) -> "StimulusTimestamps":
        stimulus_timestamps = get_ophys_stimulus_timestamps(
            sync_path=sync_file.filepath
        )
        return cls(
            timestamps=stimulus_timestamps,
            monitor_delay=monitor_delay,
            sync_file=sync_file
        )

    def from_lims(
        cls,
        db: PostgresQueryMixin,
        monitor_delay: float,
        behavior_session_id: int,
        ophys_experiment_id: Optional[int] = None
    ) -> "StimulusTimestamps":
        stimulus_file = BehaviorStimulusFile.from_lims(
                            db,
                            behavior_session_id)

        if ophys_experiment_id:
            sync_file = SyncFile.from_lims(
                db=db, ophys_experiment_id=ophys_experiment_id)
            return cls.from_sync_file(sync_file=sync_file,
                                      monitor_delay=monitor_delay)
        else:
            return cls.from_stimulus_file(stimulus_file=stimulus_file,
                                          monitor_delay=monitor_delay)

    @classmethod
    def from_nwb(cls,
                 nwbfile: NWBFile) -> "StimulusTimestamps":
        stim_module = nwbfile.processing["stimulus"]
        stim_ts_interface = stim_module.get_data_interface("timestamps")
        stim_timestamps = stim_ts_interface.timestamps[:]

        # Because the monitor delay was already applied when
        # saving the stimulus timestamps to the NWB file,
        # we set it to zero here.
        return cls(timestamps=stim_timestamps,
                   monitor_delay=0.0)

    def to_nwb(self, nwbfile: NWBFile) -> NWBFile:
        stimulus_ts = TimeSeries(
            data=self._value,
            name="timestamps",
            timestamps=self._value,
            unit="s"
        )

        stim_mod = ProcessingModule("stimulus", "Stimulus Times processing")
        stim_mod.add_data_interface(stimulus_ts)
        nwbfile.add_processing_module(stim_mod)

        return nwbfile
