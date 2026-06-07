collect_ignore_glob = []

# Disable seleniumbase pytest plugin — system-installed seleniumbase conflicts
# with pytest-html absence.  Our tests don't use seleniumbase at all.
def pytest_configure(config):
    import sys
    for plugin_name in list(sys.modules.keys()):
        if "seleniumbase" in plugin_name:
            try:
                config.pluginmanager.unregister(plugin_name)
            except Exception:
                pass
