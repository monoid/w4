#!/usr/bin/env python
import cPickle

with open('history.pickle') as inp:
    for gr in cPickle.load(inp):
        print gr.name
        print list(gr.history)
