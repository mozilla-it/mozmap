#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import click
import shutil
import requests

from ruamel import yaml
from itertools import product
from attrdict import AttrDict
from invoke import call, task, Task, Program, Collection

from leatherman.fuzzy import fuzzy
from leatherman.dbg import dbg
from leatherman.yaml import yaml_print


TASKS = (
    'dig',
    'host',
    'curl',
    '302',
    'hdrs',
    'ssl',
    'whois',
)

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

def default_output():
    return OUTPUT[int(sys.stdout.isatty())]

def output_print(obj, output):
    if output == 'yaml':
        yaml_print(obj)
    elif output == 'json':
        print(json.dumps(obj, indent=2))

@task(name='setup')
def task_setup(ctx, workdir=WORKDIR):
    print('- setup', file=sys.stderr)
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir)

@task(name='host', pre=[task_setup])
def task_host(ctx, domain, workdir=WORKDIR):
    '''run host on domain'''
    print(f'- host {domain}', file=sys.stderr)
    result = ctx.run(f'host {domain}', hide=True, warn=True)
    os.makedirs(f'{workdir}/{domain}', exist_ok=True)
    ctx.run(f'echo "{result.stdout}" > {workdir}/{domain}/host')

@task(name='dig', pre=[task_setup])
def task_dig(ctx, domain, workdir=WORKDIR):
    '''run dig on domain'''
    print(f'- dig {domain}', file=sys.stderr)
    result = ctx.run(f'dig {domain}', hide=True, warn=True)
    os.makedirs(f'{workdir}/{domain}', exist_ok=True)
    ctx.run(f'echo "{result.stdout}" > {workdir}/{domain}/dig')

@task(name='curl', pre=[task_setup])
def task_curl(ctx, domain, workdir=WORKDIR):
    '''run curl on domain'''
    print(f'- curl {domain}', file=sys.stderr)
    result = ctx.run(f'curl -L https://{domain}', hide=True, warn=True)
    os.makedirs(f'{workdir}/{domain}', exist_ok=True)
    ctx.run(f'echo "{result.stdout}" > {workdir}/{domain}/curl')

@task(name='302', pre=[task_setup])
def task_302(ctx, domain, workdir=WORKDIR):
    '''follow redirects on domain'''
    print(f'- 302 {domain}', file=sys.stderr)
    url_effective = '%{url_effective}'
    result = ctx.run(f"curl -sLD - https://{domain} -o /dev/null -w '{url_effective}'", hide=True, warn=True)
    os.makedirs(f'{workdir}/{domain}', exist_ok=True)
    ctx.run(f'echo "{result.stdout}" > {workdir}/{domain}/302')

@task(name='hdrs', pre=[task_setup])
def task_hdrs(ctx, domain, workdir=WORKDIR):
    '''grab headers from curl'''
    print(f'- hdrs {domain}', file=sys.stderr)
    result = ctx.run(f'curl -IL https://{domain}', hide=True, warn=True)
    os.makedirs(f'{workdir}/{domain}', exist_ok=True)
    ctx.run(f'echo "{result.stdout}" > {workdir}/{domain}/hdrs')

@task(name='ssl', pre=[task_setup])
def task_ssl(ctx, domain, workdir=WORKDIR, port=443, openssl_args='-noout -text'):
    '''get ssl cert info via openssl'''
    print(f'- ssl {domain}', file=sys.stderr)
    cmd = f'echo -n | openssl s_client -connect {domain}:{port} -servername {domain} 2> /dev/null | openssl x509 {openssl_args}'
    result = ctx.run(cmd, hide=True, warn=True)
    os.makedirs(f'{workdir}/{domain}', exist_ok=True)
    ctx.run(f'echo "{result.stdout}" > {workdir}/{domain}/ssl')

@task(name='whois', pre=[task_setup])
def task_whois(ctx, domain, workdir=WORKDIR):
    '''get whois info via whois cli'''
    print(f'- whois {domain}', file=sys.stderr)
    result = ctx.run(f'whois {domain}', hide=True, warn=True)
    os.makedirs(f'{workdir}/{domain}', exist_ok=True)
    ctx.run(f'echo "{result.stdout}" > {workdir}/{domain}/whois')

def task_output(ctx, workdir=WORKDIR, output=default_output()):
    '''output desc'''
    print(f'- output', file=sys.stderr)
    pairs = [
        (os.path.basename(root), file)
        for root, dirs, files in os.walk(workdir) if files
        for file in files
    ]
    result= {}
    for domain, task in pairs:
        chunk = result.get(domain, {})
        chunk[task] = open(f'{workdir}/{domain}/{task}').read().strip()
        result[domain] = chunk
    output_print(result, output)

def generate_tasks(output, tasks, domains):
    ns = Collection('tasks')
    ns.add_task(task_dig)
    ns.add_task(task_host)
    ns.add_task(task_curl)
    ns.add_task(task_302)
    ns.add_task(task_hdrs)
    ns.add_task(task_ssl)
    pre = [call(globals()[f'task_{task}'], domain) for task, domain in product(tasks, domains)]
    ns.add_task(Task(task_output, name='output', pre=pre, default=True))
    return ns

@click.command()
@click.option('-o', '--output', type=click.Choice(OUTPUT), default=default_output(), help='select output')
@click.option('-t', '--tasks', type=click.Choice(TASKS), multiple=True, help='select tasks')
@click.option('-T', '--list-tasks', is_flag=True)
@click.option('-D', '--list-domains', is_flag=True)
@click.argument('patterns', nargs=-1)
def cli(output, tasks, list_tasks, list_domains, patterns):
    tasks = tasks or TASKS
    if list_tasks:
        output_print(dict(tasks=list(tasks)), output)
        sys.exit(0)
    patterns = patterns or ('*',)
    domains = fuzzy(CFG.domains).include(*patterns)
    if list_domains:
        output_print(dict(domains=list(domains)), output)
        sys.exit(0)
    ns = generate_tasks(output, tasks, domains)
    program = Program(namespace=ns, version='0.0.1')
    exitcode = program.run([sys.argv[0], 'output', '--output', output])

if __name__ == '__main__':
    cli()
