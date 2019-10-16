'''
Implementations for the obi tasks
- obi clean
- obi stop
- obi build
- obi go
'''
from __future__ import print_function
import hashlib
import fabric
import os
import stat
import time
import yaml
import re

from fabric.api import env  # the global env variable
from fabric.api import (local, run) # the global env variable
from fabric.api import (task, parallel, runs_once) #decorators

from fabric.utils import abort
from fabric.contrib.project import rsync_project
from fabric.contrib.files import exists
import fabric.colors

# Courtesy of https://github.com/pyinvoke/invoke/issues/324#issuecomment-215289564
@task
def dryrun():
    """Show, but don't run fabric commands"""

    global local, run
    fabric.state.output['running'] = False

    # Redefine the local and run functions to simply output the command
    def local(command, capture=False, shell=None, running=None):
        print("{}".format(command))

    def run(command, shell=True, pty=True, combine_stderr=None, quiet=False,
            warn_only=False, stdout=None, stderr=None, running=None, timeout=None, shell_escape=None,
            capture_buffer_size=None):
        print("ssh -t {}@{} \"{}\"".format(env.user, env.host_string, command))

@task
@runs_once
def room_task(room_name, task_name=None):
    """
    Configures the fabric globabl env variable for other tasks
    """
    # Load the project.yaml file so we can extract configuration for the given room_name
    project_config = project_yaml()
    config = load_project_config(project_config)

    # Abort if no project name found
    project_name = config.get("name", None)
    if not project_name:
        abort("No name key found in the project.yaml. Please specify a project name")
    env.project_name = project_name
    env.local_project_dir = os.path.dirname(project_config)
    # Abort if we cannot find room_name in rooms
    rooms = config.get("rooms", {})
    room = rooms.get(room_name, None)
    if not room:
        abort("""{0} is not a room name listed in project.yaml\n
              Available room names: {1}""".format(room_name, rooms.keys()))

    # Extract the top-level config sans the rooms config
    config_no_rooms = config.copy()
    config_no_rooms.pop("rooms", None)
    # Merge the config of our room into the top-level
    env.config = config_no_rooms
    env.config.update(room)

    # Calling basename on project_name should be harmless
    # In the case that the user specified target, say, build/foo,
    # then basename gives us foo
    env.target_name = os.path.basename(
        env.config.get("target", env.project_name))

    # Running locally if:
    # - User specified is-local: True
    # - Room name is localhost
    # - Hosts is empty
    if room.get("is-local", room_name == "localhost" or not room.get("hosts", [])):
        env.hosts = ['localhost']
        env.use_ssh_config = False
        env.project_dir = env.local_project_dir
        env.file_exists = os.path.exists
        env.rsync = lambda: None # Don't rsync when running locally -- noop
        env.cd = fabric.context_managers.lcd
        # Generate a shell script that duplicates the task
        task_name = task_name or env.tasks[-1]
        env.run = local
        env.background_run = env.run
        env.relpath = os.path.relpath
        env.launch_format_str = "{0} {1}"
        env.debug_launch_format_str = "{0} {1} {2}"
    else:
        env.user = room.get("user", env.local_user) # needed for remote run
        env.hosts = room.get("hosts", [])
        env.use_ssh_config = True
        # Default remote project dir is /tmp/localusername/projectname
        env.project_dir = room.get("project-dir", default_remote_project_folder())
        env.run = run
        env.background_run = lambda cmd: env.run(cmd, pty=False)
        env.file_exists = fabric.contrib.files.exists
        env.rsync = rsync_task
        env.cd = fabric.context_managers.cd
        env.relpath = lambda p: p
        env.launch_format_str = "sh -c '(({0} nohup {1} > {2} 2> {2}) &)'"
        env.debug_launch_format_str = "tmux new -d -s {0} '{1}'".format(env.target_name, "{0} {1} {2}")
    env.build_dir = os.path.abspath(env.relpath(os.path.join(env.project_dir, env.config.get("build-dir", "build"))))

@task
@parallel
def build_task():
    """
    obi build
    """
    with env.cd(env.project_dir):
        user_specified_build = env.config.get("build-cmd", None)
        if env.config.has_key("build-cmd"):
            if user_specified_build:
                env.run(user_specified_build)
        else:
            if 'meson-args' in env.config:
                # Arguments for the meson step
                meson_args = env.config.get("meson-args", [])
                meson_args = ' '.join(map(shlexquote, meson_args))
                sentinel_hash = hashlib.sha256(meson_args).hexdigest()
            elif 'cmake-args' in env.config:
                # Arguments for the cmake step
                cmake_args = env.config.get("cmake-args", [])
                # workaround for naughty old templates
                buggy_arg = '-G "Unix Makefiles"'
                if buggy_arg in cmake_args:
                    cmake_args.remove(buggy_arg)
                    nag = 'Buggy cmake-arg {} detected in config and ignored.\n' \
                          'To avoid seeing this message, remove this entry from ' \
                          'cmake-args in project.yaml.'.format(buggy_arg)
                    print('!!!!!!!!!!!!!!!!!')
                    print('!!! BEGIN NAG !!!')
                    print('!!!!!!!!!!!!!!!!!')
                    print(nag)
                    print('(Sleeping to give you time to read this)')
                    time.sleep(4.20)
                    print('!!!!!!!!!!!!!!!!!')
                    print('!!!  END NAG  !!!')
                    print('!!!!!!!!!!!!!!!!!')
                cmake_args = ' '.join(map(shlexquote, cmake_args))
                sentinel_hash = hashlib.sha256(cmake_args).hexdigest()
            else:
                abort("Neither meson-args nor cmake-args were set in project.yaml")
            # Arguments for the build step
            build_args = env.config.get("build-args", [])
            if len(build_args) == 1 and re.match(r"^-(j|l)\d+ -(j|l)\d+$", build_args[0]):
                build_args = build_args[0].split(" ")
            build_args = " ".join(map(shlexquote, build_args))
            env.run("mkdir -p {0}".format(shlexquote(env.build_dir)))
            # If running cmake or meson succeeds, we make a file in the build directory
            # to signal to future obi processes that they don't need to re-run
            # cmake or meson (unless *-args, and therefore sentinel_hash, changes).
            # See issue #38 and issue #120
            sentinel_path = env.build_dir + "/hello-obi.txt"
            # this is a work-around for an apple bug to filter out the resulting
            # ugly linker warnings:
            # See issue 150 or:
            # https://forums.developer.apple.com/thread/97850
            warning_filter="ld: warning: text-based stub file"
            # translation from shell to pseudocode:
            #   * if the contents of SENTINEL_PATH match SENTINEL_HASH, do nothing
            #   * else if meson-args, run meson with meson-args and write SENTINEL_HASH to SENTINEL_PATH
            #   * else, run cmake with cmake-args and write SENTINEL_HASH to SENTINEL_PATH
            # Note: meson needs to be given some hints about how to find
            # a) itself, b) g-speak, and c) boost
            # Hence prepending obi_extra_path to PATH, and invoking meson with obenv.
            if 'meson-args' in env.config:
                env.run(
                    "test $(cat {sentinel_path} 2>/dev/null || echo definitelynotashahash) = {sentinel_hash} "\
                    "  || (PATH={obi_extra_path}:$PATH; obenv meson {build_dir} {meson_args} && " \
                    "      echo {sentinel_hash} > {sentinel_path})".format(
                        project_dir=shlexquote(env.project_dir),
                        build_dir=shlexquote(env.build_dir),
                        obi_extra_path = env.obi_extra_path,
                        meson_args=meson_args,
                        sentinel_path=shlexquote(sentinel_path),
                        sentinel_hash=sentinel_hash))
                env.run("set -o pipefail; ninja -C {0} {1} 2>&1 | grep -v '{2}'".
                    format(shlexquote(env.build_dir), build_args, warning_filter), shell="/bin/bash")
            elif 'cmake-args' in env.config:
                env.run(
                    "test $(cat {sentinel_path} 2>/dev/null || echo definitelynotashahash) = {sentinel_hash} "\
                    "  || (cmake -H{project_dir} -B{build_dir} {cmake_args} && " \
                    "      echo {sentinel_hash} > {sentinel_path})".format(
                        project_dir=shlexquote(env.project_dir),
                        build_dir=shlexquote(env.build_dir),
                        cmake_args=cmake_args,
                        sentinel_path=shlexquote(sentinel_path),
                        sentinel_hash=sentinel_hash))
                env.run("set -o pipefail; cmake --build {0} -- {1} 2>&1 | grep -v '{2}'".
                    format(shlexquote(env.build_dir), build_args, warning_filter), shell="/bin/bash")

@task
@parallel
def clean_task():
    """
    obi clean
    """
    with env.cd(env.project_dir):
        user_specified_clean = env.config.get("clean-cmd", None)
        if env.config.has_key("clean-cmd"):
            if user_specified_clean:
                env.run(user_specified_clean)
        else:
            clean_cmd = "rm -rf {0} || true".format(shlexquote(env.build_dir))
            env.run(clean_cmd)

@task
@parallel
def stop_task(force=False):
    """
    obi stop
    """
    with env.cd(env.project_dir):
        # fall-back to on-stop-cmds for backwards compatibility
        # TODO(jshrake): remove support for the amiguous on-stop-cmds key
        for cmd in env.config.get("pre-stop-cmds", env.config.get("on-stop-cmds", [])):
            env.run(cmd)
    with env.cd(env.project_dir):
        for cmd in env.config.get("local-pre-stop-cmds", []):
            local(cmd)

    # target_regex = find_launch_target()
    # why this funny construct? to be extremely specific about what our regex is
    # when run on a remote room, we want to match only `obi go room` invocations
    # of our current project, but launched by any user
    # if target_regex.startswith(default_remote_project_folder()):
    #     target_regex = target_regex.replace(default_remote_project_folder(),
    #                                         default_remote_project_folder().replace(
    #                                                 env.local_user,
    #                                                 "[a-z_][a-z0-9_]{0,30}"))

    signal = "SIGTERM"
    if force:
      signal = "SIGKILL"
    # temporarily ignore above code and issue signal to env.target_name because
    # target_regex won't hit webthing-enabled projects due to shell wrapper
    if env.target_name:
        default_stop = "pkill -{0} -f '[a-z/]+{1}([[:space:]]|$)' || true".format(signal, env.target_name)
    else:
        default_stop = "echo 'no pkill command issued because target=\"\"'"
    stop_cmd = env.config.get("stop-cmd", default_stop)
    env.run(stop_cmd)
    with env.cd(env.project_dir):
        for cmd in env.config.get("post-stop-cmds", []):
            env.run(cmd)
    with env.cd(env.project_dir):
        for cmd in env.config.get("local-post-stop-cmds", []):
            local(cmd)

@task
@parallel
def fetch_task(fetch_files_to_dir, files):
    """
    obi fetch
    """
    fetch_dir = fetch_files_to_dir + '/%(host)s/%(path)s'
    files_to_fetch = files or env.config.get("fetch", [])
    with env.cd(env.project_dir):
        for f in files_to_fetch:
            try:
                fabric.operations.get(f, fetch_dir)
            # dont fail when f doesn't exist on the remote machines
            except:
                continue

@task
@parallel
def launch_task(debugger, extras):
    """
    Handles launching the application in obi go
    """

    target = find_launch_target()

    launch_args = env.config.get("launch-args", [])

    formatted_launch = "{0} {1} {2}".format(
        target, # {0}
        " ".join(extras), # {1}
        " ".join(launch_args) # {2}
    )

    env_vars = env.config.get("env-vars", {})
    env_vars = " ".join(["{0}={1}".format(key, val) for key, val in env_vars.items()])

    with env.cd(env.project_dir):
        # Process pre-launch commands
        for cmd in env.config.get("pre-launch-cmds", []):
            env.run(cmd)
        if debugger:
            debug_cmd = debugger
            debuggers = env.config.get("debuggers", None)
            if debuggers:
                debug_cmd = debuggers.get(debugger, debug_cmd)
            default_launch = env.debug_launch_format_str.format(env_vars, debug_cmd, formatted_launch)
            launch_cmd = env.config.get("debug-launch-cmd", default_launch)
            env.background_run(launch_cmd)
        else:
            log_file = env.relpath(os.path.join(env.project_dir, env.target_name + ".log"))
            default_launch = env.launch_format_str.format(env_vars, formatted_launch, log_file)
            launch_cmd = env.config.get("launch-cmd", default_launch)
            env.background_run(launch_cmd)
        # Process the post-launch commands
        for cmd in env.config.get("post-launch-cmds", []):
            env.run(cmd)

@task
@parallel
def rsync_task():
    """
    Task wrapper around fabric's rsync_project
    """
    fabric.api.local(env.config.get("pre-rsync-cmd", ""))
    """ NOTE(jshrake): local_dir must end in a trailing slash
    From http://docs.fabfile.org/en/1.11/api/contrib/project.html
    - If local_dir ends with a trailing slash, the files will be
    dropped inside of remote_dir.
    E.g. rsync_project("/home/username/project/", "foldername/")
    will drop the contents of foldername inside of /home/username/project.
    - If local_dir does not end with a trailing slash
    (and this includes the default scenario, when local_dir is not
    specified), remote_dir is effectively the "parent" directory, and
    new directory named after local_dir will be created inside of it.
    So rsync_project("/home/username", "foldername") would create
    a new directory /home/username/foldername (if needed) and place the
    files there.
    """
    env.run("mkdir -p {0}".format(shlexquote(env.project_dir)))
    return fabric.contrib.project.rsync_project(
        local_dir=env.local_project_dir + "/",
        remote_dir=env.project_dir,
        delete=True,
        exclude=env.config.get("rsync-excludes", []),
        extra_opts=env.config.get("rsync-extra-opts", "--copy-links --partial"),
        capture=True)

def parent_dir(current_dir):
    """
    Returns the absolute path to the parent directory of current_dir
    """
    return os.path.abspath(os.path.join(current_dir, os.pardir))

def load_project_config(config_path):
    """
    Returns a Dict of the project.yaml specifed by config_path or aborts on
    failure
    """
    try:
        with open(config_path) as config_file:
            config = yaml.load(config_file)
            if not config:
                abort("Error: problem loading " + project_config_file)
            return config
    except Exception as e:
        abort("Cannot load project.yaml file at {0}\nException: {1}".format(config_path, e))

def project_yaml():
    """
    Returns the absolute path to the project.yaml file
    This function will search the current working directory on up to root
    If no project.yaml file is found, aborts
    """
    current = os.getcwd()
    parent = parent_dir(current)
    while current != parent:
        test_file = os.path.join(current, "project.yaml")
        if os.path.exists(test_file):
            return os.path.abspath(test_file)
        else:
            current = parent
            parent = parent_dir(current)
    abort("Could not find the project.yaml file in {0} or any parent directories".format(os.getcwd()))

# taken from https://github.com/python/cpython/blob/c80b0175c88be9611b6eea7a60104b4488839a04/Lib/shlex.py#L308
#_find_unsafe = re.compile(r'[^\w@%+=:,./-]', re.ASCII).search
_find_unsafe = re.compile(r'[^\w@%+=:,./-]').search #re.ASCII is py3
def shlexquote(s):
    """Return a shell-escaped version of the string *s*."""
    if not s: return "''"
    if _find_unsafe(s) is None: return s

    # use single quotes, and put single quotes into double quotes
    # the string $'b is then quoted as '$'"'"'b'
    return "'" + s.replace("'", "'\"'\"'") + "'"

def find_launch_target():
    """
    returns the absolute path to the binary we're going to launch
    """
    target = ""
    # Did the user specify a target?
    config_target = env.config.get("target", None)
    if config_target:
        target = os.path.join(env.project_dir, config_target)
    # TODO(jshrake): Consider nesting these conditionals
    # Look for a binary with name env.target_name in the build directory
    if not env.file_exists(target):
        target = os.path.join(env.build_dir, env.target_name)
    # Look for a binary with name env.target_name in the binary directory
    if not env.file_exists(target):
        target = os.path.join(env.project_dir, "bin", env.target_name)
    # Just give up -- can't find the target name
    if not env.file_exists(target):
        abort("Cannot find target binary to launch. Please specify the relative path to the binary via the target key")

    return target

def default_remote_project_folder():
    """
    default destination for remote runs, /tmp/localusername/projectname
    """
    return os.path.join(os.path.sep, "tmp", env.local_user, env.project_name)
