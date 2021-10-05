#!/usr/bin/env python
#
# License: https://opensource.org/licenses/MIT
# Author: Stefan Jakobs <sjakobs@anexia-it.com>
#
# Create a HTML page with a summary of all Gitlab Ansible roles
#

import yaml
# import pprint
# import requests.exceptions
import sys
import gitlab
import getopt
import re
import base64
import datetime
from termcolor import cprint
from jinja2 import Environment, FileSystemLoader, Template
from graphviz import Digraph


GITLAB_URL = 'https://gitlab.example.com'
PATH_FILTERS = []
DEST_PREFIX = 'ansible_roles'


def usage():
    """ print a help message and explain the options """
    print("Create a file called {}.html which contains an overview fo all Gitlab roles".format(DEST_PREFIX))
    print("{} [-h|--help]".format(sys.argv[0]))
    print("                -t|--token=<gitlab token>")
    print("                -g|--gitlab-url=<url>")
    print("                [-f|--filter=<path>]")
    print("")
    print("  -h|--help                 ... print this help message")
    print("  -t|--token                ... expects a gitlab access token for authentication")
    print("  -f|--filter <path filter> ... expects the beginnging of a gitlab path, e.g. so/")
    print("  -g|--gitlab-url <url>     ... URL to gitlab instance")
    print("  -U|--show-unknown         ... show unkown roles in HTML file")


def main():
    global PATH_FILTERS
    global DEST_PREFIX
    global GITLAB_URL
    try:
        opts, args = getopt.getopt(sys.argv[1:], "f:g:ht:U", [
            "filter=", "help", "token=", "show-unknown"
        ])
    except getopt.GetoptError as e:
        cprint(e, "red")    # will print something like "option -a not recognized"
        usage()
        sys.exit(2)
    token = False
    show_unknown = False
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-f", "--filter"):
            PATH_FILTERS.append(a.lstrip('/'))
        elif o in ("-g", "--gitlab-url"):
            GITLAB_URL = a
        elif o in ("-t", "--token"):
            token = a
        elif o in ("-U", "--show-unkown"):
            show_unknown = True
        else:
            assert False, "unhandled option"

    try:
        gl = gitlab.Gitlab(GITLAB_URL, private_token=token, ssl_verify=True)
        gl.auth()
    except:
        cprint('error: authentication failure', "red")
        sys.exit(1)

    projects_data = generate_projects_data(gl)
    generate_template(projects_data, PATH_FILTERS, DEST_PREFIX + '.html', show_unknown)
    generate_template(projects_data, PATH_FILTERS, DEST_PREFIX + '_incl_unknown.html', True)
    generate_dot_graph(projects_data, DEST_PREFIX + '.gv')


def set_role_attributes(project, content):
    """get informations from meta/main.yml(content) and project, structure
       and return it.
    :param project: full gl.project object (real_project)
    :param content: content of meta/main.yml
    """

    # possible values
    # state: {"role", "play", "role_extern", "role_unknown"}

    role_attr = {}
    try:
        role_attr["description"] = content["galaxy_info"]["description"]
    except KeyError:
        role_attr["description"] = ""
    try:
        role_attr["platforms"] = content["galaxy_info"]["platforms"]
    except KeyError:
        role_attr["platforms"] = []
    try:
        role_attr["galaxy_tags"] = content["galaxy_info"]["galaxy_tags"]
    except KeyError:
        role_attr["galaxy_tags"] = []
    role_attr["state"] = "role"
    role_attr["name"] = project.name
    role_attr["url"] = project.ssh_url_to_repo
    role_attr["web_url"] = project.web_url
    role_attr["group"] = re.match("^(.+)/[^/]+$", project.path_with_namespace).group(1)
    role_attr["git_tags"] = []
    # set a empty list for used_by - makes it easier to add elements later
    role_attr["used_by"] = []
    for t in project.tags.list():
        role_attr["git_tags"].append(t.attributes["name"])

    return role_attr


def set_play_attributes(project, content):
    """get informations from role/requirements.yml(content) and project, structure
       and return it.
    :param project: full gl.project object (real_project)
    :param content: content of role/requirements.yml
    """

    play_attr = {}
    play_attr["state"] = "play"
    play_attr["name"] = project.name
    play_attr["url"] = project.ssh_url_to_repo
    play_attr["web_url"] = project.web_url
    play_attr["group"] = re.match("^(.+)/[^/]+$", project.path_with_namespace).group(1)
    # set a empty list for used_by - makes it easier to add elements later
    play_attr["used_by"] = []
    play_attr["git_tags"] = []
    for t in project.tags.list():
        play_attr["git_tags"].append(t.attributes["name"])

    return play_attr


def get_yaml_content(project, path, filename):
    """ search for path/filename inside project and return the content as dictionary.
    This assumes the content is valid yaml.
    :param project: gl.project object (real_project)
    :param path: directory path inside repository_tree of default_branch
    :param filename: name of file in path which should be returned
    """

    items = []
    content = {}

    try:
        # get all files inside the meta directory
        items = project.repository_tree(path=path, ref=project.default_branch)
    except gitlab.exceptions.GitlabHttpError as e:
        cprint("error: {}".format(e), "red")
        sys.exit(255)
    except gitlab.exceptions.GitlabGetError as e:
        cprint("info: skip project '{}', because it has no files".format(project.name), "blue")
        if str(e) != '404: 404 Tree Not Found':
            cprint("error: failed to retrieving repository_tree: {}".format(e), "red")
        return content
    if len(items) > 0:
        try:
            # get meta/main.yml
            meta_main = next(f for f in items if f["name"] == filename)
        except StopIteration:
            # no meta/main.yml available - skip this project
            return content
        try:
            file_info = project.repository_blob(meta_main.get('id'))
        except gitlab.exceptions.GitlabHttpError as e:
            cprint("error: failed to retrieving file_info: {}".format(e), "red")
            return content
        # content must be a yaml file
        content = yaml.safe_load(base64.b64decode(file_info['content']))

    return content


def add_dependencies(project, prjid, dep_list, used_by_data, external):
    """add source path as dependency. If src isn't defined add just the name
    :param project: gl.project object
    :param prjid: index of the actual processed id
    :param content: list of dependencies
    :param used_by_data: dictionary which has a dependency list
    :param external: list of external project names
    """

    for dep in dep_list:
        # FIXME follow includes
        # The `if content` part from generate_projects_data() must be moved to function
        # and then the include must be followed and the data fetched again.
        # Or some other recursive lookup.
        # example:
        #     ---
        #     - include: ./plays/roles/requirements.yml
        if "include" in dep:
            cprint("error: includes are not supported. skipping '{}'".format(project.path_with_namespace), "red")
            break
        try:
            # extract the path from the source url
            dep_path_with_namespace = re.match(r'^git@{0}:(.+).git$'.format(GITLAB_URL.replace('https://', '')), dep["src"]).group(1)
        except KeyError as e:
            cprint("warning: {}->{}: dependeny has no {} (probably galaxy source), adding as external.".format(
                project.name, dep["name"], e), "yellow")
            # use name instead which must exist
            dep_path_with_namespace = dep["name"]
            external.append(dep["name"])
            # continue which will automatically add this as an unkwown source
            pass
        try:
            if prjid not in used_by_data[dep_path_with_namespace]:
                used_by_data[dep_path_with_namespace].append(prjid)
        except:
            used_by_data[dep_path_with_namespace] = [prjid]

    return used_by_data


def generate_projects_data(gl):
    """iterate over all projects and return dict with all needed data
    :param gl: Gitlab object
    """
    # projects_data
    #  [id]
    #    [name|group|description|platforms|git_tags|galaxy_tags|url|web_url|state|used_by]
    projects_data = {}
    used_by_data = {}       # path_with_namespace to list of prjids which use the project
    projects_mapping = {}   # map path_with_namespace to prjid
    projects_extern = []    # list of projects which are external

    # get all internal projects
    projects = gl.projects.list(all=True, visibility='internal')
    for p in projects:
        # skip archived projects
        if p.archived:
            cprint("info: skip project '{}', because it is archived".format(p.name), "blue")
            continue
        for path in PATH_FILTERS:
            # continue if the project's path matches one of the path filters
            if re.match(path, p.path_with_namespace):
                # get the full project object to access all attributes
                real_project = gl.projects.get(p.id)
                # print("{},{},{},{}".format(p.id,p.path_with_namespace,p.default_branch,p.ssh_url_to_repo))

                # we need to sort the project_data by name - so we create a sortable id:
                prjid = p.name + "-" + str(p.id)
                content = get_yaml_content(real_project, 'meta', 'main.yml')
                if content:
                    if isinstance(content, str):
                        # file is probably a symlink, skip
                        cprint("warning: {} has a symlink in meta/main.yml (->{})".format(p.path_with_namespace, content), "yellow")
                        continue
                    # fill the dict with data
                    projects_data[prjid] = set_role_attributes(real_project, content)
                    projects_mapping[p.path_with_namespace] = prjid

                    # find dependencies
                    if "dependencies" in content and len(content["dependencies"]) > 0:
                        used_by_data = add_dependencies(p, prjid, content["dependencies"], used_by_data, projects_extern)
                else:
                    # no role found, search for playbooks
                    content = get_yaml_content(real_project, 'roles', 'requirements.yml')

                    if(content):
                        if isinstance(content, str):
                            # file is probably a symlink, skip
                            cprint("warning: {} has a symlink in roles/requirements.yml (->{})".format(p.path_with_namespace, content), "yellow")
                            continue
                        projects_data[prjid] = set_play_attributes(real_project, content)
                        projects_mapping[p.path_with_namespace] = prjid

                        used_by_data = add_dependencies(p, prjid, content, used_by_data, projects_extern)

    # loop over used_by data and map the used_by_data to the projects_data
    # this must be done here, after the creation of projects_mapping is finished
    cnt = 0
    for dep_path_with_namespace, dep_prjid_list in used_by_data.items():
        try:
            used_by_prjid = projects_mapping[dep_path_with_namespace]
        except KeyError as e:
            cprint("error: path_with_namespace '{}' is unknown".format(e), "red")
            # need to generate a id for this unknown project
            used_by_prjid = "zzz-unknown-" + str(cnt)

            if dep_path_with_namespace in projects_extern:
                state = "role_extern"
            else:
                state = "role_unknown"

            projects_data[used_by_prjid] = {
                "web_url": '',
                "group": "unknown",
                "description": "unknown",
                "platforms": [],
                "git_tags": [],
                "galaxy_tags": [],
                "used_by": [],
                "url": '',
                "state": state,
                "name": dep_path_with_namespace,
            }
        projects_data[used_by_prjid]["used_by"] = dep_prjid_list
        cnt += 1

    return projects_data


def generate_template(data, filters, dest_file, show_unknown):
    """generate a html file from template
    :param data: project date which will be used to fill the template
    :param dest_file: save html export in this file
    :param show_unknown: pass this to the jinja2 template. If true roles_unknown will be shown.
    """

    file_loader = FileSystemLoader('templates')
    env = Environment(loader=file_loader)
    env.lstrip_blocks = True
    template = env.get_template('roles.html.j2')
    template.globals['now'] = datetime.datetime.utcnow

    output = template.render(projects_data=data, projects_filter=filters, show_unknown=show_unknown)
    with open(dest_file, 'w') as fh:
        fh.write(output)


def generate_dot_graph(data, dest_file):
    """FIXME
    :param data: data dictionary to print
    :param dest_file: print into this file
    """

    g = Digraph(
        'G', filename=dest_file, format='svg', comment='Roles and Plays',
        node_attr={'style': 'filled'}
    )
    # g.attr(rank='same')
    g.attr(label=r'Roles and Plays', labelloc='t', fontsize='30')

    color_map = {
        'role': 'lightblue',
        'role_unknown': 'red',
        'role_extern': 'yellow',
        'play': 'limegreen'
    }

    for prjid, prj in data.items():
        for usedby_id in prj["used_by"]:
            g.node(data[usedby_id]["name"], color=color_map[data[usedby_id]["state"]])
            g.node(prj["name"], color=color_map[prj["state"]])
            g.edge(data[usedby_id]["name"], prj["name"])

    g.render()


if __name__ == "__main__":
    main()
