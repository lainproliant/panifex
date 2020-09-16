# Panifex: A Python Build System Version 2.0
- Author: Lain Musgrove
- License: MIT, see LICENSE

## Overview
Panifex is a Python build system that easily allows you to tie together
various parts of a multi-stage build and to create reusable recipes.  Like the
tool it is inspired by, `make`, it is best for shell-based build processes like
compiling code, making packages, and performing pre-defined tasks, though it
is not limited to running shell commands.

Panifex 2 has been rewritten around the concept of Recipes and Artifacts, and
overcomes some of the major limitations of 1.x versions, such as an
intertwined resource injection and build resolution process that limited its
flexibility.

Panifex doesn't come with its own build recipes, but encourages the definition
and sharing of build recipes, targets, and resources via Python modules.  A
list of known recipe modules will be included here when they become available.

## Core Concepts
### Recipes
A Recipe represents a repeatable parameterized process that may depend on the
resolution of one or more other recipes (known as "inputs").  Each Recipe
results in the creation of an Artifact (known as the "output") that represents
its side-effects.  This is typically a FileArtifact representing a file on
disk, but can also be a PolyArtifact bundling multiple result artifacts, a
user-defined Artifact subclass representing pretty much anything, or a
NullArtifact indicating that there are no side effects.

### Artifacts
Artifacts represent a (preferrably but not necessarily) reversable result of
performing a Recipe.  Typically this will be a file on disk that can be
deleted during the cleaning and/or purging process.

### Resources (i.e. `@pfx.provide`)
Resources can be recipes for specific artifacts or any other objects that are
needed for building.  Resources are evaluated before recipes are resolved, so
it is important not to depend on the results of a recipe in your providers.

Resources may depend on other resources, and are evaluated using Xeno
dependency injection.  They can be defined as normal functions or `asyncio`
coroutines, and have their parameters automatically inserted by name
based on the name of other resources that are defined.  If any parameter
names are not defined as resources, a `xeno.MissingDependencyError` is thrown.

For more information about the Xeno DI framework, see [https://github.com/lainproliant/Xeno](Xeno on Github).

### Targets (i.e., `@pfx.target`)
Targets are like resources in that they are injected with resources or other
targets, but _must_ reutrn a Recipe object.  The names of `@pfx.target`
decorated functions define the list of available build targets when running
`bake`.  When calling `pfx.build` in `bake.py`, one of the names of a defined
target can be provided indicating that this is the default target to be
resolved if no other targets are specified on the command line.

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

Most critically, when a `Recipe` is provided as the `input`, `requires`, TODO 

## Example Usage
The following example defines a `bake.py` script that builds a tetris game from
its project root directory:

```
#!/usr/bin/env python
from panifex import build, sh, provide, target, default

sh.env(CC="clang", CFLAGS=("-g", "-I./include"), LDFLAGS=("-lncurses", "-lpanel"))

def compile(src):
    return sh(
        "{CC} -c {CFLAGS} {input} -o {output}",
        input=src,
        output=Path(src).with_suffix(".o"),
    )

def link(executable, objects):
    return sh("{CC} {LDFLAGS} {input} -o {output}", input=objects, output=executable)

@provide
def sources():
    return Path.cwd().glob("**/*.c")

@target
def objects(sources):
    return [compile(src) for src in sources]

@default
def executable(objects):
    return link("ntetris2", objects)

build()
```

In the above example, the following usage patterns are presented:

- `build`, `sh`, `provide`, `target`, and `default` are imported from `panifex`
    - `build` is the default build factory that `provide`, `target`, and `default`
      are bound to, and the functor that we'll need to invoke once we've defined
      all of our provides and targets.
    - `sh` is a recipe factory for generating shell-based file recipes.
    - `provide` indicates that the function provides a resource needed by other
      resources or targets, but that it is not a targetable build artifact.
    - `target` indicates that the function provides a resource needed by
      other resources or targets, and that it is a targetable build artifact.
    - `default` indicates that this function is the default targetable build
      artifact, and will be built if no targets are explicitly specified
      when invoking `bake`.
- `CC`, `CFLAGS`, and `LDFLAGS` are defined as environment variables through
    `sh.env`.  `sh.env` extends the environment of the `sh` recipe factory with
    additional variables that are interpolated into the command string and added
    to the environment of commands run with this factory.  In addition to OS
    environment variables which are added automatically as strings, lists or
    tuples can be specified in `sh.env` which will be interpolated correctly
    into command format strings.
- `compile` is defined.  It is a normal function which calls the `sh` factory to
    generate a recipe for creating an `.o` output file for the given source
    file.  `compile` is referred to as a "recipe function", because it is a
    function that generates a recipe from arguments.  Calling this function
    itself does not run any commands, but instead the recipe generated should be
    returned from a build target, where it can be built in parallel with other
    dependencies in the overall dependency tree.  The `input` and `output`
    parameters to `sh` are special and essential:
    - `output` specifies the name of the file that will be generated by the
        shell recipe.  This is used to determine if the recipe actually needs
        to be run, and identifies the file that should be cleaned up while
        cleaning.
    - `input` is optional, and specifies the file(s) that will be used to
        create the output.  If the output already exists but any of the input
        files are newer, the output will be re-created.
- `link` is defined as another recipe function for creating the final executable
    from a list of object files.
- `sources` is a provider.  It defines the list of source files to be built.
- `objects` is the first target.  It depends on `sources` because it has a
    parameter named `sources` which is automatically injected with the result
    from `sources`, that being a list of source filenames.  It uses `compile` to
    create a list of recipes and returns them.  Panifex will build these recipes
    in parallel, spawning at maximum as many simultaneous processes as the
    system has available processor cores.
- `executable` is the default target.  It depends on `objects`, and as such won't
    actually run until all of the object file recipes generated by `objects` are
    done building.  `executable` doesn't receive the list of object recipes,
    rather it receives a list containing all of the outputs specified by each
    recipe, that being a list of object filenames.

## Release Notes
### v1.0: 07/10/2020
- ***BACKWARDS INCOMPATIBLE CHANGE***: End support for class based build modules.

### v0.8: 07/04/2020 
- Updated to support Xeno's new function providers, builds no longer have to be
  modeled as classes, but `build()` must be called at the end of the script.

### v0.1: 01/02/2020
- Initial release.
