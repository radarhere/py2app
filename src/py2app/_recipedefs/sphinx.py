from modulegraph2 import BaseNode

from .._config import RecipeOptions
from .._modulegraph import ModuleGraph
from .._recipes import recipe


@recipe("sphinx", distribution="sphinx", modules=["sphinx"])
def sphinx(graph: ModuleGraph, options: RecipeOptions) -> None:
    m = graph.find_node("sphinx")
    if not isinstance(m, BaseNode) or m.filename is None:
        return None

    for name in [
        # XXX: Why this list?
        "sphinxcontrib.applehelp",
        "sphinxcontrib.devhelp",
        "sphinxcontrib.htmlhelp",
        "sphinxcontrib.jsmath",
        "sphinxcontrib.qthelp",
        "sphinxcontrib.serializinghtml",
    ]:
        graph.import_module(m, name)
