#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import doit
import json
import click
import shutil
import requests

from ruamel import yaml
from itertools import product
from attrdict import AttrDict

from doit.cmd_base import ModuleTaskLoader
from doit.doit_cmd import DoitMain

from leatherman.fuzzy import fuzzy
from leatherman.yaml import yaml_print, yaml_format
from leatherman.dbg import dbg

DOIT_CONFIG = {
    'verbosity': 2,
    'continue': True,
}

OUTPUT = [
    'json',
    'yaml',
]

WORKDIR = '.mozmap'

URL = 'https://raw.githubusercontent.com/mozilla-it/mozmap/master/mozmap.yml'
def config(url=URL):
    response = requests.get(URL)
    yml = yaml.safe_load(response.text)
    return AttrDict(yml)

CFG = config()

def get_domains(patterns):
    return fuzzy(CFG.domains).include(*patterns).defuzz() or patterns

def default_output():
    return OUTPUT[int(sys.stdout.isatty())]

def output_print(obj, output):
    if output == 'yaml':
        yaml_print(obj)
    elif output == 'json':
        print(json.dumps(obj, indent=2))

def default_processes():
    return str(int(1.5 * os.cpu_count()))

@click.group(chain=True, invoke_without_command=True)
@click.option('-v', '--version', is_flag=True, help='print version')
@click.option('-w', '--workdir', metavar='PATH', default=WORKDIR, help='set workdir')
@click.option('-p', '--patterns', metavar='PN', default=('*'), multiple=True, help='patterns to match domains')
@click.option('-n', '--num-processes', metavar='INT', default=default_processes(), help='num processes')
@click.option('-o', '--output', type=click.Choice(OUTPUT), default=default_output(), help='select output type')
@click.pass_context
def cli(ctx, version, workdir, patterns, num_processes, output):
    if version:
        print('version: 0.0.1')
    ctx.ensure_object(AttrDict)
    ctx.obj.workdir = workdir
    ctx.obj.patterns = patterns
    if version:
        print('print version')
        sys.exit(0)


def load_tasks(tasks):
    task_names = []
    for task in tasks:
        task_names += [task.__name__[len('task_'):]]
        globals()[task.__name__] = task
    return task_names

def create_result(workdir, output):
    print('---', flush=True)
    pairs = [
        (os.path.basename(root), file)
        for root, dirs, files in os.walk(workdir) if files
        for file in files
    ]
    result = {}
    for domain, task in pairs:
        chunk = result.get(domain, {})
        chunk[task] = open(f'{workdir}/{domain}/{task}').read().strip()
        result[domain] = chunk
    output_print(result, output)

@cli.resultcallback()
def process_pipeline(tasks, *args, version=None, workdir=None, patterns=None, num_processes=None, output=None, **kwargs):
    dbg(kwargs)
    doit_args = ['-n', num_processes, '--continue']
    task_names = load_tasks(tasks)
    if not task_names:
        domains = get_domains(patterns)
        task_names = load_tasks([
            gen_task(workdir, domains, port=443) for gen_task in (gen_dig, gen_host, gen_ssl)
        ])
    def task_setup():
        return {
            'actions': [
               f'rm -rf {workdir}',
            ],
        }
    globals()[task_setup.__name__] = task_setup
    exitcode = DoitMain(ModuleTaskLoader(globals())).run(doit_args + task_names)
    create_result(workdir, output)
    sys.exit(exitcode)

@cli.command()
@click.pass_context
@click.option('-p', '--patterns', metavar='PN', multiple=True, help='patterns help')
def show(ctx, patterns, **kwargs):
    domains = get_domains(patterns or ctx.obj['patterns'])
    yaml_print(dict(domains=list(domains)))
    sys.exit(0)

def gen_dig(workdir, domains, **kwargs):
    def task_dig():
        for domain in domains:
            yield {
                'name': domain,
                'task_dep': [
                    'setup',
                ],
                'actions': [
                    f'mkdir -p {workdir}/{domain}',
                    f'dig +short {domain} > {workdir}/{domain}/dig 2>&1 || true',
                ]
            }
    return task_dig

@cli.command()
@click.pass_context
@click.option('-p', '--patterns', metavar='PN', multiple=True, help='patterns help')
def dig(ctx, patterns, **kwargs):
    domains = get_domains(patterns or ctx.obj['patterns'])
    return gen_dig(ctx.obj.workdir, domains)

def gen_host(workdir, domains, **kwargs):
    def task_host():
        for domain in domains:
            yield {
                'name': domain,
                'task_dep': [
                    'setup',
                ],
                'actions': [
                    f'mkdir -p {workdir}/{domain}',
                    f'host {domain} > {workdir}/{domain}/host 2>&1 || true',
                ]
            }
    return task_host

@cli.command()
@click.option('-p', '--patterns', metavar='PN', multiple=True, help='patterns help')
@click.pass_context
def host(ctx, patterns, **kwargs):
    domains = get_domains(patterns or ctx.obj.patterns)
    return gen_host(ctx.obj.workdir, domains)

def gen_ssl(workdir, domains, port, **kwargs):
    def task_ssl():
        openssl_args = '-noout -text'
        for domain in domains:
            cmd = f'echo -n | openssl s_client -connect {domain}:{port} -servername {domain} 2> /dev/null | openssl x509 {openssl_args} > {workdir}/{domain}/ssl 2>&1 || true'
            yield {
                'name': domain,
                'task_dep': [
                    'setup',
                ],
                'actions': [
                    f'mkdir -p {workdir}/{domain}',
                    f'{cmd}',
                ],
            }
    return task_ssl

@cli.command()
@click.option('-p', '--patterns', metavar='PN', multiple=True, help='patterns help')
@click.option('-P', '--port', default=443, help='specify port')
@click.pass_context
def ssl(ctx, patterns, port=443, **kwargs):
    domains = get_domains(patterns or ctx.obj.patterns)
    return gen_ssl(ctx.obj.workdir, domains, port)

if __name__ == '__main__':
    cfg = AttrDict()
    cli(obj=cfg)
