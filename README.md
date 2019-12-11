# obi
```
obi is a command-line tool for developing g-speaky applications.

Available tasks:

go                Build, stop, and run the project (optionally, on numerous machines)
                  defaults to deploying to /tmp/yourusername/projectname
stop              Stops the application (optionally, on numerous machines)
build             Builds the project (optionally, on numerous machines)
clean             Clean the build directory (optionally, on numerous machines)
rsync             Rsync your local project directory to remote machines
fetch             Download remote files to your local project directory

new               Generate a new project, scaffolded from an obi template
template list     List obi templates
template install  Install an obi template
template remove   Remove an installed obi template
template upgrade  Upgrade an installed obi template

room list         List available rooms

Edit project.yaml (in your project folder) to configure sets of machines for
go/stop, set arguments for building and launching the program, and choose feld &
screen proteins. By default, running your application in a room will deploy
project files to /tmp/yourusername/project-name/ on the machines of that room.

Usage:
  obi go [<room>] [--debug=<debugger>] [--dry-run] [--] [<extras>...]
  obi stop [<room>] [-f|--force] [--dry-run]
  obi build [<room>] [--dry-run]
  obi clean [<room>] [--dry-run]
  obi rsync <room> [--dry-run]
  obi fetch <room> [<file>...] [--dry-run]
  obi new <template> <name> [--template_home=<path>] [--g_speak_home=<path>]
  obi template list [--template_home=<path>]
  obi template install <giturl> [<name>] [--template_home=<path>]
  obi template remove <name> [--template_home=<path>]
  obi template upgrade [--all|<name>] [--template_home=<path>]
  obi room list
  obi -h | --help | --version

Options:
  -h --help               Show this screen.
  --version               Show version.
  --dry-run               Optional: output the list of commands that the task runs.
  --g_speak_home=<path>   Optional: absolute path of g-speak dir to build against.
  --template_home=<path>  Optional: path containing installed obi templates.
  --debug=<debugger>      Optional: launches the application in a debugger.
```

* [Install](#install)
  - [Mac](#mac)
  - [Ubuntu](#ubuntu)
* [Templates](#templates)
* [Tasks](#tasks)
* [Editor tips](#editor-tips)

## Install

### Mac (via Homebrew)

```bash
# Install homebrew
ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

# Install from Oblong's homebrew-tools tap @ github.com/Oblong/homebrew-tools
brew install Oblong/tools/obi

# Upgrading
brew update && brew upgrade obi
```

### Ubuntu 18.04 (via pip)

```bash
# Install dependencies (if using system python)
sudo apt-get install python2-dev python-pip libffi-dev libssl-dev

# Install
# NOTE: You should make sure that ~/.local/bin is on your PATH if using the
# --user flag.
pip2 install --user git+https://github.com/Oblong/obi.git

# Upgrading
pip2 install --upgrade --user git+https://github.com/Oblong/obi.git

# Uninstalling
pip2 uninstall oblong-obi
```

If conflicts arise between python3 and python2, uninstall `oblong-obi` as above, then reinstall by replacing `pip2` in the above commands with `python2 -m pip`:
```bash
python2 -m pip install --user git+https://github.com/Oblong/obi.git

# for upgrading
python2 -m pip upgrade --user git+https://github.com/Oblong/obi.git
```

## Templates

### Installing

Install templates from a git repository:
```bash
# a good batteries-included starting point project template
obi template install https://github.com/Oblong/obi-greenhouse.git greenhouse

# a very basic C++ project template
obi template install https://github.com/Oblong/obi-cpp.git cpp

# a gspeak project template
obi template install https://github.com/Oblong/obi-gspeak.git gspeak
```

The install command clones the specified repo to
`~/.local/share/oblong/obi` (or `${XDG_DATA_HOME}/oblong/obi` if that
environment variable is set). Feel free to manage this directory
yourself!

### Upgrading

```bash
obi template upgrade obi-cpp
obi template upgrade greenhouse
obi template upgrade growroom
```

Runs `git pull` in the appropriate repository.

```bash
obi template upgrade --all
```

Upgrades all installed obi templates.

### Removing

```bash
obi template remove obi-cpp
obi template remove greenhouse
obi template remove growroom
```

Removes the template.

## Tasks

### obi template list
---
`obi template list` Returns a list of installed obi templates available for use with the `new` task.

#### example
```bash
obi template list
```

### obi new [template] [name]
---
`obi new <template> <name>` generates a new project in your current working directory, scaffolded from the chosen template.

#### options
- `[--g_speak_home=<path>]`: Builds the project against the specified g-speak. Path must be an absolute path to the g-speak home directory.

If the `--g_speak_home` option is not specified, obi attempts to find a default version of gspeak that will work well for your system. It will look for the `G_SPEAK_HOME` environment variable, and finally fallback to extracting for the highest version g-speak found in `/opt/oblong/`.

#### example
```bash
obi new greenhouse app-name --g_speak_home=/opt/oblong/g-speak3.26
```

### obi go [room-name]
---
`obi go [room-name]` builds and runs the application on the machines belonging to the named room.
If `<room-name>` is not specified, then the application is built and ran on the local machine.

#### options
- `[--debug=<debugger>]`: Specify a toolname to launch the application. This is useful for launching the application with debuggers or profilers:
```bash
obi go --debug="lldb --"
obi go roomname --debug="strace --"
obi go roomname --debug="gdb -ex run --args"
```

Users can specify special names debuggers in the `project.yaml`

```yaml
# Debuggers to use in obi go --debug=<debugger>
debuggers:
  gdb: "gdb -ex run --args"
  lldb: "lldb --"
  strace: "sudo strace"
  apitrace: "apitrace trace"
```

And use them like so:
```bash
obi go --debug=lldb
obi go roomname --debug=gdb
```

When using `--debug` with a remote set of machines, the application is launched in a tmux session with a name matching the target name. This allows one to ssh into one of the machines, attach to the tmux session and poke around:

```bash
obi go roomname --debug=gdb
ssh -t user@host-in-roomname tmux attach -t targetname
```

This assumes that tmux is installed on the remote machines.

#### example

```bash
# Launch the application on the local machine
obi go
# Launch application on the host machines listed under the room named room
obi go room
# Launch the application with lldb
obi go --debug="lldb --"
# Launch the application with apitrace in a remote room
obi go room --debug="apitrace trace"
```

### obi stop [room-name]
---
`obi stop [<room-name>]` stops the application. If `<room-name>` is not specified, then the application is stopped on the local machine. The `[-f|--force]` option
will send a stronger message, such as SIGKILL.

#### example
```bash
# Stop the application on the local machine
obi stop
# Stop the application on the host machines listed under the room named room
obi stop room
# Forcefully stop the application on remote hosts for the room named room
obi stop room -f
```

### obi build [room-name]
---
`obi build [<room-name>]` builds the application. If `<room-name>` is not specified, then the application is built on the local machine.

#### example
```bash
# Build the application on the local machine
obi build
# Build the application on the host machines listed under the room named room
obi build room
```

### obi clean [room-name]
---
`obi clean [<room-name>]` cleans (deletes) the build directory. If `<room-name>` is not specified, then the build directory on the local machine is cleaned.

#### example
```bash
# Clean the application build directory on the local machine
obi clean
# Clean the application build directory on the host machines listed under the room named room
obi clean room
```

## SSH tips

obi depends on having passwordless SSH access to remote hosts. If you're running
on a mac and having SSH troubles, make sure your SSH keys are loaded into your
key agent. On mac, you can add this to your `~/.ssh/config`:
```
Host *
  UseKeychain yes
  AddKeysToAgent yes
```
Alternatively, you can add this script snippet to your shell startup:
```
eval "$(ssh-agent -s)"
ssh-add -K ~/.ssh/id_rsa
```

## Bash command completion

obi ships with a tab-completion script for bash. When you install obi with homebrew,
the script is installed to `/usr/local/etc/bash_completion.d/obi`. Add a snippet
like the following to your preferred bash config file:
```bash
if [ -f /usr/local/etc/bash_completion.d/obi ]; then
  source /usr/local/etc/bash_completion.d/obi
fi
```
zsh users can use the same file, by adding a similar snippet to their `.zshrc`:
```zsh
if [ -f /usr/local/etc/bash_completion.d/obi ]; then
  autoload bashcompinit
  bashcompinit
  source /usr/local/etc/bash_completion.d/obi
fi
```
If you installed obi by using `pip`, you will need to install the command completion
script manually.

## Editor tips

### emacs

obi works well out of the box with emacs's
[compilation][emacs-compilation] feature.  `M-x compile<RET>obi go
[room-name]` from a file in the root directory of the project will run
obi as a subprocess of emacs and pipe the output to a `*compilation*`
buffer (which can support obi's use of
[ANSI colors][colorize-compilation]).  Compile errors are picked up by
emacs, and you can navigate directly to the error's location using the
ordinary features of [compilation mode][emacs-comp-mode].  To kill an
obi invocation in the compilation buffer, use `M-x kill-compilation`.

[emacs-compilation]: http://www.gnu.org/software/emacs/manual/html_node/emacs/Compilation.html
[emacs-comp-mode]: http://www.gnu.org/software/emacs/manual/html_node/emacs/Compilation-Mode.html
[colorize-compilation]: http://stackoverflow.com/a/3072831/692055
