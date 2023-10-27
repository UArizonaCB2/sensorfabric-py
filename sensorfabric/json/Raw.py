""""
    Date : 06-22-2022
    Author : Shravan Aras
    Email : shravanaras@arizona.edu

    This file contains methods used to parse raw json sensor data files.
"""

import sys
import json
import re
import gzip

def scanJsonFile(filename):
    """
    Description
    -----------
    Method which is able to read a general JSON file and output its structure
    along with various stat elements. Usefuly for understanding large json files.
    This method supports both .json and .json.gz files.
    Important - This method does not parse file headers to determine file types,
    but only the extensions.

    Parameters
    ----------
    filename - Full path of the file.
    Note - This loads the whole file into memory. Be aware of that.
    """
    jpattern = r"\.json$"
    jzpattern = r"\.json.gz$"
    json_buffer = []
    try:
        if re.search(jpattern, filename):
            f = open(filename, 'r')
        elif re.search(jzpattern, filename):
            f = gzip.open(filename, mode='rt')
        else:
            raise Exception('File extension must be either .json or .json.gz')
    except FileNotFoundError as err:
        print('Invalid file path')
        return (False, [])

    assert(f != None)

    # Assuming the json is serialized, and each line has one
    # fully formed json.
    line = 1
    item = f.readline()
    while len(item) > 0:
        try:
            json_data = json.loads(item)
            json_buffer.append(json_data)
        except json.decoder.JSONDecodeError as err:
            print('Unable to decode json on line {}'.format(line))

        line +=1
        item = f.readline()

    f.close()

    return (True, json_buffer)

# This method is used to pretty print the json schema.
# We use a depth first approach to recursively print it.
def prettyPrintSchema(json_data, level=0, showType=False):
    for k in json_data.keys():
        # Print those dam dashes.
        for i in range(0, level):
            print('-', end='')
    
        # Json array.
        if type(json_data[k]) == type(list()):
            print('{} : Array of length {}'.format(k, len(json_data[k])))
            if len(json_data[k]) > 0:
                prettyPrintSchema(json_data[k][0], level+1, showType)
        elif type(json_data[k]) == type(dict()):
            print(k)
            prettyPrintSchema(json_data[k], level+1, showType)
        else:
            if showType:  
                print('{} : Type of {}'.format(k, type(json_data[k])))
            else:
                print('{}'.format(k))

"""
Method which takes a query to be applied on JSON.
The current grammar for query syntax is as follows 

Query : [Operation] [Selector] FROM [Path] | 
        [Operation] [Selector] FROM [Path] [Modifier]
Operation : SELECT
Selector : * | [Field]
Modifier : [Limit] <int>
Path : [Field] | [Field].[Path]
Field : <string>

Tokens - [SELECT, FROM]

All inbuild tokens must be upper case. Good luck pressing that SHIFT key.

This method only takes a single line of query. It is very dumb and basic.
"""
def execQuery(json_data, query):
    assert(type(query) == type(str()))
    if len(query) <= 0:
        print("You can't pass me a blank query!")

    # Break the query into tokens.
    tokens = query.split(' ')
    if len(tokens) < 0:
        print('Malformed Query')
        return (False, None)

    if tokens[0] == 'SELECT':
        return __selectQuery(json_data, tokens[1:])

    return (True, None)

"""
Select operation query
"""
def __selectQuery(json_data, tokens):
    assert(json_data != None)
    assert(json_data != None)

    if len(tokens) < 3:
        print('Malformed SELECT query')
        return (False, None)

    # Get the various portions of this query (Lazy AST)
    selector = tokens[0]
    if not (selector == '*' or type(selector) == type(str())):
        print('Selector needs to be * or string')
        return (False, None)

    # Check if the FROM token is there.
    if not tokens[1] == 'FROM':
        print('Expected FROM in statement')
        return (False, None)

    # Check if the path argument is a string.
    if not type(tokens[2]) == type(str()):
        print('Path must be a string')
        return (False, None)

    path = tokens[2]
    selector = tokens[0]

    # Check if the path is correct.
    hops = path.split('.')
    if len(hops) <= 0:
        print('Invalid path structure statement')
        return (False, None)

    """
    SELECT value FROM activities-heart-intraday.dataset
    """
    """
    We do not support indexing into nested arrays. Only single level arrays
    are currently supported.
    """
    head = json_data
    for h in hops:
        if h in head.keys():
            head = head[h]
        else:
            print('Invalid hop "{}" in "{}"'.format(h, path))
            return (False, None)

    # Head can be either a dict() or an array[]. Cannot be a 
    # leaf node in JSON.
    if not (type(head) == type(dict()) or type(head) == type(list())):
        print('Path cannot end at a leaf node')
        return (False, None)

    # We make sure the selector is in the path and we can return that.
    if type(head) == type(dict()):
        if selector in head.keys():
            return (True, head[selector])
    if type(head) == type(list()):
        # We need to make in memory list to add things to and then return.
        buffer = []
        for h in head:
            if type(h) == type(dict()) and selector in h.keys():
                buffer.append(h[selector])
        return (True, buffer)

    return (False, None)


# Method which gracefully fails and returns a None if there is an Index error.
def __safeIndex(expression):
    try:
        exec(expression)
    except IndexError as err:
        return None
