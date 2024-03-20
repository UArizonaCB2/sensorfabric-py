""""
    Date : 10-24-2023
    Author : Shravan Aras
    Email : shravanaras@arizona.edu

    Flatten the json into a data-frame / table for structured analysis.
"""

import json
import pandas
import numpy as np

def flatten(json_data : json, base_path='', sep='_', fill=True) -> dict:
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
    Returns a dictionary object with the keys as columns.
    """

    # Append a key to the base path.
    appendPath = lambda p, k : k if len(p) <= 0 else p+sep+k

    if type(json_data) == type(dict()):
        #frame = pandas.DataFrame()
        frame = {}
        for k in json_data.keys():
            f = flatten(json_data[k], appendPath(base_path, k), sep, fill)
            # Special case : If we are concating a frame of shape 1xm with nxp
            # then the based on the `fill` argument we will expand the 1xm frame to nxm
            # frame before concatinating. Hence filling the empty spaces and causing
            # redandant data.
            if fill:
                if len(list(frame.items())) < len(list(f.items())):
                    frame = _filler(frame, f)
                elif len(list(frame.items())) > len(list(f.items())):
                    f = _filler(f, frame)
            # These need to be concatinated along the column axis.
            #frame = pandas.concat([frame, f], axis=1)
            frame = _concat(frame, f)
        return frame
    elif type(json_data) == type(list()):
        # For each element in the list recursively call the flattener and append to existing frame.
        #frame = pandas.DataFrame()
        frame = {}
        for ele in json_data:
            f = flatten(ele, base_path, sep, fill)
            # These need to be concatinated along the index axis.
            #frame = pandas.concat([frame, f], axis=0, ignore_index=True)
            frame = _concat(frame, f)
        return frame
    else:
        #return pandas.DataFrame({base_path:json_data}, index=[0])
        return {base_path:json_data}

def _concat(dictA, dictB):
    """
    Merges the contents of dictionary B into A
    """
    for k in dictB.keys():
        if not(k in dictA):
            dictA[k] = []
        if type(dictB[k]) == type(list()):
            dictA[k].extend(dictB[k])
        else:
            dictA[k].append(dictB[k])

    return dictA

def _isSimpleJson(obj):
    for k in obj.keys():
        if type(obj[k]) == type(dict()) or type(obj[k]) == type(list()):
            return False
    return True

    
def _filler(small : dict, big : dict) -> dict:
    """
    Extend the smaller dictionary to match the big on.
    """

    targetCount = 0
    for k in big.keys():
        if type(big[k]) == type(list()):
            if len(big[k]) > targetCount:
                targetCount = len(big[k])

    for k in small.keys():
        if not(type(small[k]) == type(list())):
            small[k] = [small[k]] # If it is not a list we make it into a list.
        if len(small[k]) < targetCount:
            lastElement = small[k][-1]
            for i in range(len(small[k]), targetCount):
                small[k].append(lastElement)

    return small
