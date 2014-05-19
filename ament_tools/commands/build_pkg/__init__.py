# Copyright 2014 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

from ament_package import package_exists_at
from ament_package import parse_package
from ament_package import PACKAGE_MANIFEST_FILENAME
import argparse
import os
from pkg_resources import iter_entry_points
import subprocess
import sys

AMENT_COMMAND_BUILD_PKG_BUILD_TYPES_ENTRY_POINT = 'ament.command.build_pkg.build_types'


def main(args):
    parser = build_pkg_parser()
    ns, unknown_args = parser.parse_known_args(args)

    package = parse_package(ns.path)
    build_type = get_build_type(package)

    entry_points = list(iter_entry_points(group=AMENT_COMMAND_BUILD_PKG_BUILD_TYPES_ENTRY_POINT, name=build_type))
    assert len(entry_points) <= 1
    if not entry_points:
        print("The '%s' file in '%s' exports an unknown build types: %s" % (PACKAGE_MANIFEST_FILENAME, ns.path, build_type), file=sys.stderr)
        return 1
    entry_point = entry_points[0]

    return entry_point.load()(args)


def get_build_type(package):
    build_types = [e for e in package.exports if e.tagname == 'build_type']
    if len(build_types) > 1:
        print("The '%s' file in '%s' exports multiple build types" % (PACKAGE_MANIFEST_FILENAME, ns.path), file=sys.stderr)
    if not build_types:
        build_types.append('ament_cmake')
    return build_types[0]


def build_pkg_parser(build_type=None):
    description = entry_point_data['description']
    prog = 'ament build_pkg'
    if build_type:
        description += " with build type '%s'" % build_type
        prog += '_%s' % build_type
    parser = argparse.ArgumentParser(
        description=description,
        prog=prog,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        'path',
        nargs='?',
        type=existing_package,
        default=os.curdir,
        help='Path to the package',
    )
    parser.add_argument(
        '--build-prefix',
        default='/tmp/ament_build_pkg/build',
        help='Path to the build prefix',
    )
    parser.add_argument(
        '--install-prefix',
        default='/tmp/ament_build_pkg/install',
        help='Path to the install prefix',
    )
    return parser


def existing_package(path):
    if not os.path.exists(path):
        raise argparse.ArgumentTypeError("Path '%s' does not exist" % path)
    if not os.path.isdir(path):
        raise argparse.ArgumentTypeError("Path '%s' is not a directory" % path)
    if not package_exists_at(path):
        raise argparse.ArgumentTypeError(
            "Path '%s' does not contain a '%s' file" %
            (path, PACKAGE_MANIFEST_FILENAME))
    return path


def run_command(cmd, cwd=None):
    msg = '# Invoking: %s' % ' '.join(cmd)
    if cwd:
        msg += ' (in %s)' % cwd
    print(msg)
    return subprocess.check_call(cmd, cwd=cwd)


# meta information of the entry point
entry_point_data = dict(
    description='Build a package',
    main=main,
)
