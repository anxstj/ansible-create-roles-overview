# ansible-create-roles-overview

## Overview

The script `./create_roles_overview.py` queries a Gitlab API for Ansible
roles and playbooks. It will iterate over **all** projects and check if
a project contains Ansible code. From the found roles and playbooks it
will generate a dependency graph.

This was tested with Gitlab 14.1.

### Usage

```
./create_roles_overview.py -t mygitlabtoken -g https://gitlab.example.com
```

The above command will create the following files:

* `ansible_roles.gv`: dot file which contains the hierarchy description
* `ansible_roles.gv.svg`: svg which show a representation of the dot graph
* `ansible_roles.html`: HTML file that contains a table with all found roles
  and playbooks
* `ansible_roles_incl_unknown.html`: As above, but with unknown roles as well

### Gitlab CI example

```
stages:
  - run

test:
  image: python:3.9-slim
  stage: run
  script:
    - pip install --no-cache-dir -r requirements.txt
    - ./create_roles_overview.py --token "$CI_JOB_TOKEN" --filter myproject/
```

## License

Copyright 2021 Anexia

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

