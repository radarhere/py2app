"""
Wrapper around class:`modulegraph2.ModuleGraph` with additional
functionality useful for py2app.
"""

import contextlib
import importlib.resources
import io
import os
import typing

import modulegraph2
from modulegraph2 import (
    AliasNode,
    BaseNode,
    BuiltinModule,
    ExcludedModule,
    ExtensionModule,
    FrozenModule,
    MissingModule,
    Module,
    NamespacePackage,
    Package,
    PyPIDistribution,
    Script,
)

from ._config import Resource

ATTR_ZIPSAFE = "py2app.zipsafe"
ATTR_BOOTSTRAP = "py2app.bootstrap"
ATTR_IGNORE_RESOURCES = "py2app.ignore_resources"
ATTR_RESOURCES = "py2app.resources"
ATTR_EXPECTED_MISSING = "py2app.expected_missing"


def load_bootstrap(bootstrap: typing.Union[str, io.StringIO]) -> str:
    """
    Load a bootstrap script and return the script text
    """
    if isinstance(bootstrap, io.StringIO):
        return bootstrap.read()

    else:
        package, _, fname = bootstrap.partition(":")
        return (
            importlib.resources.files(package)
            .joinpath(fname)
            .read_text(encoding="utf-8")
        )


class _ChangeTracker:
    __slots__ = ("updated",)

    def __init__(self) -> None:
        self.updated = False


class ModuleGraph(modulegraph2.ModuleGraph):
    """
    Subclass of *modulegraph2.ModuleGraph* that adds some
    py2app-specific functionality.
    """

    #
    # Note: All "add_" methods should ensure that they are idempotent
    #       when adding the same value more than once because resources
    #       can be run multiple times while building the graph.
    def __init__(
        self, *, use_stdlib_implies: bool = True, use_builtin_hooks: bool = True
    ):
        super().__init__(
            use_stdlib_implies=use_stdlib_implies, use_builtin_hooks=use_builtin_hooks
        )
        self.__tracked_changes: typing.List[_ChangeTracker] = []

    @contextlib.contextmanager
    def tracked_changes(self) -> typing.Iterator[_ChangeTracker]:
        """
        Contextmanager for detecting if the graph was updated by adding
        nodes or edges to the graph.
        """
        # XXX: This currently assumes code uses the modulegraph2 API and
        #      does not add nodes or edges through the lower-level
        #      objectgraph API.
        # XXX: This is magic enough that the tracker mechanism should be
        #      moved to objectgraph.
        tracker = _ChangeTracker()
        self.__tracked_changes.append(tracker)
        try:
            yield tracker
        finally:
            self.__tracked_changes.remove(tracker)

    def __set_updated(self) -> None:
        """
        Set the "updated" flag to true for all active change trackers
        """
        for tracker in self.__tracked_changes:
            tracker.updated = True

    def add_module(self, module_name: str) -> BaseNode:
        node = self.find_node(module_name)
        if node is not None:
            assert isinstance(node, BaseNode)
            return node

        self.__set_updated()
        return super().add_module(module_name)

    def add_script(self, script_path: os.PathLike) -> Script:
        node = self.find_node(str(script_path))
        if node is not None:
            assert isinstance(node, Script)
            return node
        self.__set_updated()
        return super().add_script(script_path)

    def import_package(self, importing_module: BaseNode, package_name: str) -> BaseNode:
        # XXX: This is not good enough, will result in false positive update
        #      value if import_package was called earlier
        node = self.find_node(package_name)
        if node is not None:
            assert isinstance(node, BaseNode)
            if node.extension_attributes.get("py2app.full_package", False):
                return node
        self.__set_updated()
        node = super().import_package(importing_module, package_name)
        assert isinstance(node, BaseNode)
        node.extension_attributes["py2app.full_package"] = True
        return node

    def import_module(self, importing_module: BaseNode, module_name: str) -> BaseNode:
        node = self.find_node(module_name)
        if node is not None:
            assert isinstance(node, BaseNode)
            try:
                self.edge_data(importing_module, node)
            except KeyError:
                pass

            else:
                return node

        self.__set_updated()
        return super().import_module(importing_module, module_name)

    def add_distribution(
        self, distribution: typing.Union[PyPIDistribution, str]
    ) -> typing.Union[PyPIDistribution, str]:
        # XXX: Need check if there actually is an update
        self.__set_updated()
        return super().add_distribution(distribution)

    def set_expected_missing(self, node: MissingModule) -> None:
        """
        Mark *node* as expected missing
        """
        node.extension_attributes[ATTR_EXPECTED_MISSING] = True

    def is_expected_missing(self, node: BaseNode) -> bool:
        """
        Return true if node is expected missing, and false otherwise
        """
        return node.extension_attributes.get(ATTR_EXPECTED_MISSING, False)

    def add_resources(
        self,
        node: typing.Union[BaseNode, PyPIDistribution],
        resources: typing.List[Resource],
    ) -> None:
        """
        Add a resource definition for *node*. The *resources*
        specify files that should be copied into the bundle
        when this node is included (but aren't part of the
        package resources as defined by *importlib.resources*).

        The same resource definition will not be added more
        than once.
        """
        node_resources = node.extension_attributes.setdefault(ATTR_RESOURCES, [])
        node_resources.extend(rsrc for rsrc in resources if rsrc not in node_resources)

    def resources(
        self, node: typing.Union[BaseNode, PyPIDistribution]
    ) -> typing.List[Resource]:
        """
        Return the resources that should be copied into the bundle
        for *node* (excluding resources as defined by *importlib.resources*
        """
        return node.extension_attributes.get(ATTR_RESOURCES, [])

    def set_ignore_resources(
        self, node: typing.Union[BaseNode, PyPIDistribution]
    ) -> None:
        """
        Mark *node* as a node whose package resources should not
        be copied into the bundle.
        """
        node.extension_attributes[ATTR_IGNORE_RESOURCES] = True

    def ignore_resources(self, node: typing.Union[BaseNode, PyPIDistribution]) -> bool:
        """
        Return true iff the package resources for *node* should
        not be copied into the bundle.
        """
        return node.extension_attributes.get(ATTR_IGNORE_RESOURCES, False)

    def add_bootstrap_scriptlet(
        self, node: typing.Union[BaseNode, PyPIDistribution], bootstrap_source: str
    ) -> None:
        """
        Add a bundle bootstrap scriptlet for a particular node in the graph

        The method will add each bootstrap scriptlet at most once.
        """
        if bootstrap_source in node.extension_attributes.get(ATTR_BOOTSTRAP, []):
            return

        node.extension_attributes.setdefault(ATTR_BOOTSTRAP, []).append(
            bootstrap_source
        )

        self.add_dependencies_for_source(bootstrap_source)

    def add_bootstrap(
        self,
        node: typing.Union[BaseNode, PyPIDistribution],
        bootstrap: typing.Union[str, io.StringIO],
    ) -> None:
        """
        Add a bundle bootstrap scriptlet for a particular node in the graph.

        The method will add each bootstrap scriptlet at most once.
        """
        bootstrap_source = load_bootstrap(bootstrap)
        self.add_bootstrap_scriptlet(node, bootstrap_source)

    def bootstrap(
        self, node: typing.Union[BaseNode, PyPIDistribution]
    ) -> typing.Optional[str]:
        """
        Return the bootstrap scriptlet for a node, or None when
        the node doesn't have a bootstrap scriptlet.
        """
        value = node.extension_attributes.get(ATTR_BOOTSTRAP, None)
        if value:
            return "\n".join(value)

        return None

    def mark_zipunsafe(self, node: typing.Union[BaseNode, PyPIDistribution]) -> None:
        """
        Mark *node* as unsafe to be executed from a zip archive
        """
        node.extension_attributes[ATTR_ZIPSAFE] = False

    def is_zipsafe(self, node: typing.Union[BaseNode, PyPIDistribution]) -> bool:
        """
        Return False if *node* cannot be executed from a zip archive,
        return True otherwise.

        For this method extension modules are assumed to be just
        like other modules, even though Python's extension loader
        cannot load extensions from a zipfile.
        """
        if not isinstance(node, (Module, Package, NamespacePackage)):
            return True

        try:
            value = node.extension_attributes[ATTR_ZIPSAFE]
        except KeyError:
            pass
        else:
            assert isinstance(value, bool)
            return value

        if isinstance(node, Module) and node.uses_dunder_file:
            return False

        elif isinstance(node, Package):
            if ATTR_ZIPSAFE in node.init_module.extension_attributes:
                if not node.init_module.extension_attributes[ATTR_ZIPSAFE]:
                    node.extension_attributes[ATTR_ZIPSAFE] = False
                    return False
            elif (
                isinstance(node.init_module, Module)
                and node.init_module.uses_dunder_file
            ):
                node.extension_attributes[ATTR_ZIPSAFE] = False
                return False

        #
        # Package, and all modules in them, are either zipsafe or
        # note. We cannot have a package that is zipsafe but containing
        # modules or subpackages that aren't.
        #

        if "." in node.identifier:
            # The name is in package, use the root package to start
            # the scan.
            base = self.find_node(node.identifier.partition(".")[0])

            # Node is inside a package, the package itself should
            # be part of the graph.
            assert base is not None
        elif isinstance(node, (Package, NamespacePackage)):
            base = node
        else:
            # By default standalone modules are zipsafe
            return True

        base_identifier = f"{base.identifier}."

        # This function uses the 'py2app.zipsafe' attribute to cache
        # the zipsafe status of a package.
        try:
            value = base.extension_attributes[ATTR_ZIPSAFE]
        except KeyError:
            pass
        else:
            assert isinstance(value, bool)
            return value

        for subnode in self.iter_graph():
            if not subnode.identifier.startswith(base_identifier):
                continue

            if subnode.extension_attributes.get(ATTR_ZIPSAFE, None) is False:
                base.extension_attributes[ATTR_ZIPSAFE] = False
                return False

        base.extension_attributes[ATTR_ZIPSAFE] = True
        return True

    def collect_nodes(
        self,
    ) -> typing.Tuple[typing.List[BaseNode], typing.List[BaseNode]]:
        """
        Return 2 lists:
            1. Nodes to include in the zipfile (this includes Extensions)
            2. Nodes that should be kept outside of the zipfile
        """
        zip_nodes: typing.List[BaseNode] = []
        unzip_nodes: typing.List[BaseNode] = []

        for node in self.iter_graph():
            if isinstance(
                node,
                (
                    BuiltinModule,
                    FrozenModule,
                    AliasNode,
                    MissingModule,
                    ExcludedModule,
                    PyPIDistribution,
                ),
            ):
                continue

            if isinstance(node, ExtensionModule) and "." not in node.identifier:
                # Toplevel extension modules are always kept outside of the zipfile
                unzip_nodes.append(node)
            elif self.is_zipsafe(node):
                zip_nodes.append(node)
            else:
                unzip_nodes.append(node)

        return zip_nodes, unzip_nodes

    def add_post_processing_hook(
        self, hook: typing.Callable[["ModuleGraph", BaseNode], None]
    ) -> None:
        # XXX: The typing.cast here is an indication that I'm using typing wrong
        super().add_post_processing_hook(
            typing.cast(
                typing.Callable[[modulegraph2.ModuleGraph, BaseNode], None], hook
            )
        )
