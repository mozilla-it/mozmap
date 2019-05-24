#!/usr/bin/env python3
# -*- coding: utf-8 -*-
version = 'v1'

import os
import re
import sys
import inspect
sys.dont_write_bytecode = True

SCRIPT_FILE = os.path.abspath(__file__)
SCRIPT_NAME = os.path.basename(SCRIPT_FILE)
SCRIPT_PATH = os.path.dirname(SCRIPT_FILE)
NAME, EXT = os.path.splitext(SCRIPT_NAME)
if os.path.islink(__file__):
    REAL_FILE = os.path.abspath(os.readlink(__file__))
    REAL_NAME = os.path.basename(REAL_FILE)
    REAL_PATH = os.path.dirname(REAL_FILE)

import requests

from ruamel import yaml
from argparse import ArgumentParser, RawDescriptionHelpFormatter

from leatherman.dbg import dbg
from leatherman.fuzzy import fuzzy

DEFAULT = '\033[0;0m'
GREEN   = '\033[01;32m'
RED     = '\033[01;31m'


URL = 'https://raw.githubusercontent.com/mozilla-it/mozmap/master/mozmap.yml'
OUTPUTS = [
    'yaml',
    'json',
]

# the following colorize code was taken from here and slighly modified
# src: https://stackoverflow.com/a/6196103
def colorize(stdout_color, stderr_color, enabled=True):
    '''
    colorize: decorator for functions that print to stdout or stderr
    '''

    def apply_colorize(func):
        class ColorWrapper(object):
            def __init__(self, wrapee, color):
                self.wrapee = wrapee
                self.color = color
            def __getattr__(self, attr):
                if attr == 'write' and self.wrapee.isatty():
                    return lambda x: self.wrapee.write(self.color + x + DEFAULT)
                else:
                    return getattr(self.wrapee, attr)

        def wrapper(*args, **kwds):
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = ColorWrapper(old_stdout, stdout_color)
            sys.stderr = ColorWrapper(old_stderr, stderr_color)
            try:
                func(*args, **kwds)
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        return wrapper if enabled else func

    return apply_colorize

class MozMap():
    '''
    MozMap: calss for handling all actions with domains
    '''
    def __init__(self):
        '''
        init
        '''
        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        self.do_methods = {
            name[3:]: method for name, method in methods if name.startswith('do_')
        }

    def execute(self, args):
        '''
        execute: function to parse args and execute the appropriate actions
        '''
        parser = ArgumentParser(
            add_help=False)
        parser.add_argument(
            '-C', '--config',
            metavar='CONFIG',
            default=URL,
            help=f'default="{URL}"; config location')
        ns, rem = parser.parse_known_args(args)
        try:
            config = yaml.safe_load(open(ns.config))
        except FileNotFoundError as er:
            config = dict()
        parser = ArgumentParser(
            parents=[parser],
            description=__doc__,
            formatter_class=RawDescriptionHelpFormatter)
        parser.set_defaults(**config)
        parser.add_argument(
            '--output',
            metavar='OUTPUT',
            choices=OUTPUTS,
            default=OUTPUTS[0],
            help=f'default="{OUTPUTS[0]}"; choices="{OUTPUTS}"; output format ')
        subparsers = parser.add_subparsers(
            dest='command',
            title='commands',
            description='choose command to run')
        subparsers.required = True
        [self.add_command(subparsers, name, method) for name, method in self.do_methods.items()]
        self.ns = parser.parse_args(rem)
        dbg(ns=self.ns)
        self.ns.func(**self.ns.__dict__)

    def add_command(self, subparsers, name, method):
        '''
        add_command: adds a subcommand to MozMap, grabs parser arguments from the do_ function
        '''
        parser = subparsers.add_parser(name)
        parser.set_defaults(func=method)
        method(parser=parser)
        return parser

    @colorize(GREEN, RED)
    def print_stdout(self, stdout, verbose):
        '''
        print_stdout: colorized function to print stdout
        '''
        if stdout and verbose:
            print(stdout)

    @colorize(GREEN, RED)
    def print_stderr(self, stderr, verbose):
        '''
        print_stderr: colorized function to print stderr
        '''
        if stderr and verbose:
            print(stderr, file=sys.stderr)

    def do_list(self, parser=None, patterns=None, **kwargs):
        '''
        do_list: list all of the domains matching the patterns
        '''
        if parser:
            parser.add_argument(
                'patterns',
                metavar='PATTERNS',
                nargs='+',
                help='one or more domain patterns')
        if not patterns:
            patterns = ['*']

    def do_test(self, parser=None, patterns=None, **kwargs):
        '''
        do_test: run tests against domains matching the patterns
        '''
        if not patterns:
            patterns = ['*']
        if parser:
            parser.add_argument(
                'patterns',
                metavar='PATTERNS',
                nargs='+',
                help='one or more domain patterns')

if __name__ == '__main__':
    mozmap = MozMap()
    mozmap.execute(sys.argv[1:])

