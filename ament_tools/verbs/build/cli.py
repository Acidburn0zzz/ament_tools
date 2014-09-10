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

import os
import sys

from osrf_pycommon.cli_utils.verb_pattern import call_prepare_arguments

from ament_tools.build_type_discovery import yield_supported_build_types
from ament_tools.helper import argparse_existing_dir
from ament_tools.helper import combine_make_flags
from ament_tools.helper import determine_path_argument
from ament_tools.helper import extract_argument_group
from ament_tools.topological_order import topological_order
from ament_tools.verbs.build_pkg import main as build_pkg_main
from ament_tools.verbs.build_pkg import TestError


def argument_preprocessor(args):
    """Run verb and build_type plugin preprocessors on arguments.

    The preprocessors take in raw arguments and return potentially trimmed
    arguments and extra options to be added to the argparse NameSpace object.

    :param list args: list of arguments as str's
    :returns: tuple of left over arguments and dictionary of extra options
    :raises: SystemError if underlying assumptions are not met
    """
    extras = {}

    # Extract make arguments
    args, make_flags = extract_argument_group(args, '--make-flags')

    # For each available build_type plugin, let it run the preprocessor
    for build_type in yield_supported_build_types():
        build_type_impl = build_type.load()()
        args, tmp_extras = build_type_impl.argument_preprocessor(args)
        extras.update(tmp_extras)

    combine_make_flags(make_flags, args, extras)

    return args, extras


def prepare_arguments(parser, args):
    """Add parameters to argparse for the build verb and available plugins.

    After adding the generic verb arguments, this function loads all available
    build_type plugins and then allows the plugins to add additional arguments
    to the parser in a new :py:class:`argparse.ArgumentGroup` for that
    build_type.

    :param parser: ArgumentParser object to which arguments are added
    :type parser: :py:class:`argparse.ArgumentParser`
    :param list args: list of arguments as str's
    :returns: modified version of the original parser given
    :rtype: :py:class:`argparse.ArgumentParser`
    """
    # Add verb arguments
    parser.add_argument(
        '-C', '--directory',
        default=os.curdir,
        help="The base path of the workspace (default '%s')" % os.curdir
    )
    parser.add_argument(
        'basepath',
        nargs='?',
        type=argparse_existing_dir,
        default=os.path.join(os.curdir, 'src'),
        help="Base path to the packages (default 'CWD/src')",
    )
    parser.add_argument(
        '--build-space',
        help="Path to the build space (default 'CWD/build')",
    )
    parser.add_argument(
        '--install-space',
        help="Path to the install space (default 'CWD/install')",
    )
    parser.add_argument(
        '--test',
        action='store_true',
        default=False,
        help='Enable testing of packages',
    )
    parser.add_argument(
        '--abort-test-error',
        action='store_true',
        default=False,
        help='Stop after tests with errors or failures',
    )
    parser.add_argument(
        '--start-with',
        help='Start with a particular package',
    )
    parser.add_argument(
        '--make-flags',
        help='Flags to be passed to make by build types which invoke make'
    )

    # Allow all available build_type's to provide additional arguments
    for build_type in yield_supported_build_types():
        build_type_impl = build_type.load()()
        group = parser.add_argument_group("'{0}' build_type options"
                                          .format(build_type_impl.build_type))
        call_prepare_arguments(build_type_impl.prepare_arguments, group, args)

    return parser


def main(opts):
    # use PWD in order to work when being invoked in a symlinked location
    cwd = os.getenv('PWD', os.curdir)
    opts.directory = os.path.abspath(os.path.join(cwd, opts.directory))
    if not os.path.exists(opts.basepath):
        raise RuntimeError("The specified base path '%s' does not exist" %
                           opts.basepath)
    opts.build_space = determine_path_argument(cwd, opts.directory,
                                               opts.build_space, 'build')
    opts.install_space = determine_path_argument(cwd, opts.directory,
                                                 opts.install_space, 'install')

    packages = topological_order(opts.basepath)
    package_names = [p.name for _, p in packages]

    if opts.start_with and opts.start_with not in package_names:
        sys.exit("Package '{0}' specified with --start-with was not found."
                 .format(opts.start_with))

    print('')
    print('# Topological order')
    start_with_found = not opts.start_with
    for (path, package) in packages:
        if package.name == opts.start_with:
            start_with_found = True
        if not start_with_found:
            print(' skip %s' % package.name)
        else:
            print(' -    %s' % package.name)
    print('')

    any_test_errors = False
    start_with_found = not opts.start_with
    for (path, package) in packages:
        if package.name == opts.start_with:
            start_with_found = True
        if not start_with_found:
            print('# Skipping: %s' % package.name)
            continue
        pkg_path = os.path.join(opts.basepath, path)

        print('')
        print('# Building: %s' % package.name)
        print('')
        opts.path = pkg_path
        try:
            rc = build_pkg_main(opts)
        except TestError as e:
            if opts.abort_test_error:
                return str(e)
            rc = None
            any_test_errors = True
        if rc:
            return rc

    if any_test_errors:
        return 1
