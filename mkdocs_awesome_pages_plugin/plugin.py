import warnings
from typing import List, Dict

from mkdocs.config import config_options, Config
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import Files, File
from mkdocs.structure.nav import (
    Navigation as MkDocsNavigation,
    get_navigation,
    Section,
    Link,
)
from mkdocs.structure.pages import Page

from .meta import DuplicateRestItemError, MetaNavRestItem, RestItemList
from .navigation import AwesomeNavigation, get_by_type, NavigationItem, get_awesome_navigation
from .options import Options


class NavPluginOrder(Warning):
    def __init__(self, plugin_name: str):
        super().__init__(
            'The plugin "{plugin_name}" might not work correctly when placed before awesome-pages in the list of '
            "plugins. It defines an on_nav handler that will be overridden by awesome-pages in some circumstances.".format(
                plugin_name=plugin_name
            )
        )


class AwesomePagesPlugin(BasePlugin):

    DEFAULT_META_FILENAME = ".pages"
    REST_PLACEHOLDER = "AWESOME_PAGES_REST"

    config_scheme = (
        ("filename", config_options.Type(str, default=DEFAULT_META_FILENAME)),
        ("collapse_single_pages", config_options.Type(bool, default=False)),
        ("strict", config_options.Type(bool, default=True)),
    )

    def __init__(self):
        self.nav_config_with_rest = None
        self.rest_items = RestItemList()
        self.rest_blocks = {}
        self.rest_dict = {}

    def on_nav(self, nav: MkDocsNavigation, config: Config, files: Files):
        explicit_nav = nav if not config["nav"] else None
        
        if self.nav_config_with_rest:
            # restore explicit config with rest placeholder and build nav
            config["nav"] = self.nav_config_with_rest
            awesome_nav = get_awesome_navigation(files, config)
            
            explicit_nav = get_navigation(files, config)

            for key, value in self.rest_dict.items(): # Add "rest sections" back to nav
                rest_link = Link(AwesomePagesPlugin.REST_PLACEHOLDER, value)
                explicit_nav.items.insert(key, rest_link)
            
        explicit_sections = set(get_by_type(explicit_nav, Section)) if explicit_nav else set()

        if self.nav_config_with_rest:
            self.rest_blocks = self._generate_rest_blocks(awesome_nav.items, [page.file for page in explicit_nav.pages])
            self._insert_rest(explicit_nav.items) 
            nav = explicit_nav

        return AwesomeNavigation(nav.items, Options(**self.config), config["docs_dir"], explicit_sections).to_mkdocs()

    def on_config(self, config: Config):
        for name, plugin in config["plugins"].items():
            if name == "awesome-pages":
                break
            if hasattr(plugin, "on_nav"):
                warnings.warn(NavPluginOrder(name))

        if config["nav"]:
            self._find_rest(config["nav"])
            if self.rest_items:
                self.nav_config_with_rest = config["nav"]

                self.temp_nav_config = config["nav"]

                for index,item in enumerate(config["nav"]):
                    if type(item) is dict: 
                        if AwesomePagesPlugin.REST_PLACEHOLDER in item:
                            self.rest_dict.update({index:item[AwesomePagesPlugin.REST_PLACEHOLDER]})
                            self.temp_nav_config.pop(index)

                config["nav"] = self.temp_nav_config  # Leave non "rest-like" nav, namely for Blog validation
                
        return config

    def _find_rest(self, config):
        if isinstance(config, list):
            for index, element in enumerate(config):
                if MetaNavRestItem.is_rest(element):
                    rest_item = MetaNavRestItem(element)
                    if rest_item in self.rest_items:
                        raise DuplicateRestItemError(rest_item.value, "mkdocs.yml")
                    self.rest_items.append(rest_item)

                    config[index] = {AwesomePagesPlugin.REST_PLACEHOLDER: "/" + element}
                else:
                    self._find_rest(element)

        elif isinstance(config, dict):
            for value in config.values():
                self._find_rest(value)

    def _generate_rest_blocks(
        self, items: List[NavigationItem], exclude_files: List[File]
    ) -> Dict[str, List[NavigationItem]]:
        result = {rest_item: [] for rest_item in self.rest_items}
        for item in items[:]:  # loop over a shallow copy of items so removing items doesn't break iteration
            if isinstance(item, Page):
                if item.file not in exclude_files:
                    for rest_item in self.rest_items:
                        if rest_item.matches(item.file.src_path):
                            items.remove(item)
                            result[rest_item].append(item)
                            break
            if isinstance(item, Section):
                child_result = self._generate_rest_blocks(item.children, exclude_files)
                for rest_item, children in child_result.items():
                    if children:
                        if rest_item.flat:
                            result[rest_item].extend(children)
                        else:
                            result[rest_item].append(Section(item.title, children))
        return result

    def _insert_rest(self, items):
        for index, item in enumerate(items):
            if isinstance(item, Link) and item.title == AwesomePagesPlugin.REST_PLACEHOLDER:
                items[index : index + 1] = self.rest_blocks[MetaNavRestItem(item.url[1:])]
            if isinstance(item, Section):
                self._insert_rest(item.children)