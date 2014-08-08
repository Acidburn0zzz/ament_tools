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

import argparse
import inspect
import os
import pkg_resources
import subprocess
import sys

from ament_package import package_exists_at
from ament_package import PACKAGE_MANIFEST_FILENAME
from ament_package import parse_package

from ament_tools.context import Context

from osrf_pycommon.cli_utils.verb_pattern import call_prepare_arguments

AMENT_BUILD_PKG_BUILD_TYPES_ENTRY_POINT = 'ament.verb.build_pkg.build_types'


def add_path_argument(parser):
    """Add position path argument to parser."""
    parser.add_argument(
        'path',
        nargs='?',
        default=os.curdir,
        help='Path to the package',
    )


def argument_preprocessor(args):
    """Run verb and plugin preprocessors on arguments.

    The preprocessors take in raw arguments and return potentially trimmed
    arguments and extra options to be added to the argparse NameSpace object.

    This can fail if the positional path argument does not contain a valid path
    or if the build type of the package at that path does not have a
    corresponding build type plugin.

    :param list args: list of arguments as str's
    :returns: tuple of left over arguments and dictionary of extra options
    :raises: SystemError if underlying assumptions are not met
    """
    extras = {}

    # Detected build type if possible
    parser = argparse.ArgumentParser()
    add_path_argument(parser)
    opts, _ = parser.parse_known_args(args)
    try:
        path = validate_package_manifest_path(opts.path)
    except (MissingPluginError, ValueError) as exc:
        sys.exit("{0}".format(exc))
    build_type = get_build_type(path)
    build_type_impl = get_class_for_build_type(build_type)()
    # Let detected build type plugin do argument preprocessing
    args, extras = build_type_impl.argument_preprocessor(args)
    return args, extras


def prepare_arguments(parser, args):
    """Add parameters to argparse for the build_pkg verb and its plugins.

    After adding the generic verb arguments, this function tries to determine
    the build type of the target package. This is done by gracefully trying
    to get the positional ``path`` argument from the arguments, falling back
    to the default ``os.curdir``. Then it searches for a package manifest in
    that path. If it finds the package manifest it then determines the build
    type of the package, e.g. ``ament_cmake``. It then trys to load a build
    type plugin for that build type. If the loading is successful it will allow
    the plugin to add additional arguments to the parser in a new
    :py:class:`argparse.ArgumentGroup` for that build type.

    :param parser: ArgumentParser object to which arguments are added
    :type parser: :py:class:`argparse.ArgumentParser`
    :param list args: list of arguments as str's
    :returns: original parser given
    :rtype: :py:class:`argparse.ArgumentParser`
    """
    # Add verb arguments
    add_path_argument(parser)
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

    # Detected build type if possible
    try:
        # Remove -h and --help to prevent printing help messages
        filt_args = list(filter(lambda x: x not in ['-h', '--help'], args))
        # Remove first position argument, because that will be the verb
        for i, arg in enumerate(filt_args):
            if not arg.startswith('-'):
                del filt_args[i]
                break
        # Parse the arguments to find the user's provided path (or the default)
        opts, _ = parser.parse_known_args(filt_args)
        # Check to ensure the path has a package
        path = validate_package_manifest_path(opts.path)
        # Get the build_type from the package manifest
        build_type = get_build_type(path)
        # Find an entry point which supports this build type
        build_type_impl = get_class_for_build_type(build_type)()
        # Let the detected build type plugin add arguments
        group = parser.add_argument_group(
            "{0} (detected) options".format(build_type_impl.build_type))
        call_prepare_arguments(
            build_type_impl.prepare_arguments,
            group,
            args,
        )
    # Catch value and system errors which will raise later
    # This is done to preserve -h and --help's ability to function
    except (MissingPluginError, ValueError) as exc:
        # If system exit AND -h or --help are used, show the error
        if '-h' in args or '--help' in args:
            print("Error: Could not detect package build type:", exc)
    return parser


def yield_supported_build_types(name=None):
    return pkg_resources.iter_entry_points(
        group=AMENT_BUILD_PKG_BUILD_TYPES_ENTRY_POINT,
        name=name,
    )


class MissingPluginError(Exception):
    pass


def get_class_for_build_type(build_type):
    """Gets the class for a given package build type.

    :param str build_type: name of build_type plugin, e.g. 'ament_cmake'
    :returns: class for the requirest build_type plugin
    :raises: RuntimeError if there are more than one plugins for a requested
        build type.
    :raises: MissingPluginError if there is no plugin for the requested
        build type.
    """
    entry_points = list(yield_supported_build_types(build_type))
    if len(entry_points) > 1:
        # Shouldn't happen, defensive
        raise RuntimeError("More than one build_type entry_point.")
    if len(entry_points) == 0:
        raise MissingPluginError(
            "No plugin to handle a package with build_type '{0}'"
            .format(build_type)
        )
    return entry_points[0].load()

package_manifest_cache_ = {}


def __get_cached_package_manifest(path):
    global package_manifest_cache_
    if path not in package_manifest_cache_:
        package_manifest_cache_[path] = parse_package(path)
    return package_manifest_cache_[path]


def get_build_type(path):
    """Extract the build_type from the package manifest at the given path.

    If the package manifest does not have an explict build_type the default
    'ament_cmake' is used.

    :param str path: path to a package manifest file
    :returns: build_type as a string
    """
    package = __get_cached_package_manifest(path)

    build_type_exports = [e for e in package.exports
                          if e.tagname == 'build_type']
    if len(build_type_exports) > 1:
        print("The '%s' file in '%s' exports multiple build types" %
              (PACKAGE_MANIFEST_FILENAME, path), file=sys.stderr)

    default_build_type = 'ament_cmake'
    if not build_type_exports:
        return default_build_type

    return build_type_exports[0].content


def validate_package_manifest_path(path):
    """Assert the given path is a directory with a manifest or the manifest.

    :param str path: directory containing a package manifest file or the file
    :returns: path to the manifest file, not just the directory
    :rtype: str
    :raises: ValueError if path is not valid or does not contain manifest
    """
    p = path
    if not os.path.isdir(p):
        p = p.rstrip('/')
        if p.endswith(PACKAGE_MANIFEST_FILENAME):
            p = p[:-len(PACKAGE_MANIFEST_FILENAME)]
    if not os.path.isdir(p):
        raise ValueError("Path '{0}' is not a directory or does not exist"
                         .format(p))
    if not package_exists_at(p):
        raise ValueError("Path '{0}' does not contain a '{1}' manifest file"
                         .format(p, PACKAGE_MANIFEST_FILENAME))
    return p


def handle_build_action(build_action_ret, context):
    build_action_ret
    if not inspect.isgenerator(build_action_ret):
        return
    for build_action in build_action_ret:
        if build_action.type == 'command':
            print("==> '{0}'".format(" ".join(build_action.cmd)))
            subprocess.check_call(build_action.cmd, cwd=context.build_space)
        elif build_action.type == 'function':
            raise NotImplementedError
        else:
            raise RuntimeError("Unknown BuildAction type '{0}'"
                               .format(build_action.type))


def main(opts):
    try:
        opts.path = validate_package_manifest_path(opts.path)
    except ValueError as exc:
        sys.exit("Error: {0}".format(exc))
    # Load up build type plugin class
    build_type = get_build_type(opts.path)
    build_type_impl = get_class_for_build_type(build_type)()
    # Setup build_pkg common context
    context = Context()
    context.source_space = os.path.abspath(os.path.normpath(opts.path))
    context.package_manifest = __get_cached_package_manifest(opts.path)
    pkg_name = context.package_manifest.name
    context.build_space = os.path.join(opts.build_prefix, pkg_name)
    context.install_space = opts.install_prefix
    context.install = True
    context.isolated_install = False
    context.symbolic_link_install = False
    context.make_flags = []
    context.dry_run = False
    print("Build package '{0}' with context:".format(pkg_name))
    print("-" * 80)
    keys = ['source_space', 'build_space', 'install_space', 'make_flags']
    max_key_len = str(max([len(k) for k in keys]))
    for key in keys:
        value = context[key]
        if isinstance(value, list):
            value = ", ".join(value) if value else "None"
        print(("{0:>" + max_key_len + "} => {1}").format(key, value))
    print("-" * 80)
    # Allow the build type plugin to process options into a context extender
    ce = build_type_impl.extend_context(opts)
    # Extend the context with the context extender
    ce.apply_to_context(context)
    # Run the build command
    print("+++ Building '{0}'".format(pkg_name))
    on_build_ret = build_type_impl.on_build(context)
    handle_build_action(on_build_ret, context)
    # Run the install command
    print("+++ Installing '{0}'".format(pkg_name))
    on_install_ret = build_type_impl.on_install(context)
    handle_build_action(on_install_ret, context)
