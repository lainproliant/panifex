# NOTE - DEPRECATION
This package is now superceeded by `xeno.build` in the `xeno` package,
see https://github.com/lainproliant/xeno

# Panifex: A Python Build Automation System -- Version 2.0
- Author: Lain Musgrove
- License: MIT, see LICENSE

## Overview
> (panifex (latin) - m (genitive panificis); third declension)
>   1. a baker, breadmaker

Panifex is a build automation system built around recipes and their resulting
artifacts.

Panifex is built atop [Xeno](https://github.com/lainproliant/xeno), a
Python-based dependency injection framework, which it uses to semantically
construct recipes based on a tree of dependencies.

Like in `make(3)`, build targets are defined by instructions used to construct
them and their dependencies.  Unlike `make(3)`, these relationships are defined
in Python code, and targets can be either shell-based recipes or custom
recipies written in Python.

Like `make(3)`, Panifex determines if a recipe needs to be re-built by
comparing the age of the artifacts if they exist and the artifacts of all
dependant recipes.

## Installation
Panifex requires python-3.8 or later.  To install, simply run:

```sh
sudo pip install panifex
```

## Simple Example
```python
from panifex import build, target, sh

@target
def hello():
    return sh("echo 'Hello' >> {output}",
              output='hello.txt')

@target
def world():
    return sh("echo 'World' >> {output}",
              output='world.txt')

@target
def hello_world(hello, world):
    return sh("cat {input} >> {output}",
              input=[hello, world],
              output='helloworld.txt')

build(hello_world)
```

To run this example, copy it into a file called `bake.py`, then run `bake`[^1] on
the command line.

```sh
bake
```

In this example, we're using `sh()`, which is the shell recipe factory.  The
parameters `input=` and `output=` are special for `sh()`, because they define the
dependencies and artifacts of the shell recipe respectively.[^2]  We define
three targets: `hello`, `world`, and `hello_world` which is the default target.
`hello_world` depends on the output of `hello` and `world` and uses them to
construct a third file, `helloworld.txt`.

The `@target` annotation is used to define the given function as a build
target.  Each named parameter to the function must be the name of a target or
other resource[^3], and is automatically provided with the value of that
resource when it is being defined.  When specified on the command line by name,
a target can be invoked.  The target and all of its dependencies will be built.
If no target is specified, the target passed to `build()` is used by default.

`build()` is the function that kicks off the build process, and should be
placed in your `bake.py` after all of your targets are defined.

[^1]: `bake` is a command provided by Panifex which executes `bake.py` in the
  current directory if it exists, and has various switches for other operations
  such as cleaning, listing targets, and printing a diagnostic build tree.  For
  more information, run `bake --help`.

[^2]: For shell recipes, `requires=` can be used to declare additional
  dependencies, whether or not these dependencies are used in the actual shell
  command.

[^3]: Panifex also offers `@provide` for defining a resource that is available
  but that is not a build target.  Usually, this is for statically defined
  resources or enumerations that are not recipies, such as lists of input
  files.

## Core Concepts
### Recipes
A *recipe* represents a repeatable process that produces one or more artifacts.

### Artifacts
Artifacts represent a potentially reversable result of a recipe.  Often they
will represent a file or directory on disk that can be deleted by cleaning.

### Resources and Targets
*Resources* (via `@provide`) are functions that return recipes or other data
needed by other parts of your build process.  *Targets* (via `@target`) are
resources that can be invoked as build targets via the `bake` command.

Resources can return recipes or any other objects that are needed for building, though *targets* must return a recipe.

Resources are evaluated before recipes are resolved, so it is important not to
depend on the results of a recipe in your providers.

Resources may depend on other resources, and are evaluated using
[Xeno](https://github.com/lainproliant/xeno).  They can be defined as normal
functions or `asyncio` coroutines, and have their parameters automatically
inserted by name based on the name of other resources that are defined.  If any
parameter names are not defined as resources, a `xeno.MissingDependencyError`
is thrown.

### Contextual Inferences
While some situations will require you to extend `pfx.recipes.Recipe` and
`pfx.artifacts.Artifact` to define your own specialized versions of these
concepts, most of the time `FileArtifact`, `ValueArtifact`, and simple recipes
can be constructed using contextual inferences.  For example, when a string or
`pathlib.Path` object is passed in the `output`, `input`, or `requires`
parameters of a `ShellRecipe` (created via `sh` or the `ShellFactory`), it is
inferred that this value refers to a FileArtifact.  In the case of `output`,
it indicates that the given value is the file or file(s) that are created as a
result of resolving the recipe.

## Concrete Example
The following example defines a `bake.py` script that builds a tetris game from
its project root directory:

```python
#!/usr/bin/env python
from panifex import build, sh, provide, target, recipe

sh.env(CC="clang", CFLAGS=("-g", "-I./include"), LDFLAGS=("-lncurses", "-lpanel"))

@recipe
def compile(src):
    return sh(
        "{CC} -c {CFLAGS} {input} -o {output}",
        input=src,
        output=Path(src).with_suffix(".o"),
    )

@recipe
def link(executable, objects):
    return sh("{CC} {LDFLAGS} {input} -o {output}", input=objects, output=executable)

@provide
def sources():
    return Path.cwd().glob("**/*.c")

@target
def objects(sources):
    return [compile(src) for src in sources]

@target
def executable(objects):
    return link("ntetris", objects)

build(executable)
```

An even richer example can be found in the [bake.py for Jotdown on Github](https://github.com/lainproliant/jotdown/blob/master/bake.py).

## Release Notes
### v2.0: 09/17/2020
- ***BACKWARDS INCOMPATIBLE CHANGE***: Switch to Recipes and Artifacts model after major refactoring.

### v1.0: 07/10/2020
- ***BACKWARDS INCOMPATIBLE CHANGE***: End support for class based build modules.

### v0.8: 07/04/2020 
- Updated to support Xeno's new function providers, builds no longer have to be
  modeled as classes, but `build()` must be called at the end of the script.

### v0.1: 01/02/2020
- Initial release.
