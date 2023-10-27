""""
    Date : 10-24-2023
    Author : Shravan Aras
    Email : shravanaras@arizona.edu

    Flatten the json into a data-frame / table for structured analysis.
"""

import json
import pandas
import numpy as np

def flatten(json_data : json, base_path='', sep='_', fill=True) -> pandas.DataFrame:
    """
    Description
    -----------
    This method is used to flatten a json object by recursively parsing it.
    Memory Warning : Note that this method heavily makes use of the stack for
                recursive operations. It can cause your process to run out of memory
                for deeply nested json objects, or very large json objects.

    Parameters
    ----------
    json_data : json
        The JSON object to parse.
    base_path : str
        Default value of ''. Base path is prepended with all field names created
        for this dataframe.

    Returns
    -------
    Returns a pandas dataframe.
    """

    # Append a key to the base path.
    appendPath = lambda p, k : k if len(p) <= 0 else p+sep+k

    if type(json_data) == type(dict()):
        frame = pandas.DataFrame()
        for k in json_data.keys():
            f = flatten(json_data[k], appendPath(base_path, k), sep)
            # Special case : If we are concating a frame of shape 1xm with nxp
            # then the based on the `fill` argument we will expand the 1xm frame to nxm
            # frame before concatinating. Hence filling the empty spaces and causing
            # redandant data.
            if fill:
                if frame.shape[0] == 1 and f.shape[0] > 1:
                    frame = _filler(frame, f)
                elif f.shape[0] == 1 and frame.shape[0] > 1:
                    f = _filler(f, frame)
            # These need to be concatinated along the column axis.
            frame = pandas.concat([frame, f], axis=1)
        return frame
    elif type(json_data) == type(list()):
        # For each element in the list recursively call the flattener and append to existing frame.
        frame = pandas.DataFrame()
        for ele in json_data:
            f = flatten(ele, base_path, sep)
            # These need to be concatinated along the index axis.
            frame = pandas.concat([frame, f], axis=0, ignore_index=True)
        return frame
    else:
        return pandas.DataFrame({base_path:json_data}, index=[0])

def _filler(small : pandas.DataFrame, big : pandas.DataFrame) -> pandas.DataFrame:
    cols = small.columns
    map = {}
    for c in cols:
        map[c] = [small.at[0, c]] * big.shape[0]

    return pandas.DataFrame(map)
