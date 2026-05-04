import importlib

import click

from config.config import Configs
from utils.log_common import build_logger

logger = build_logger()

_LAZY_COMMAND_MODULES = {
    "start": "startup",
    "vulnbot": "pentest",
    "pentestgpt": "experiment.pentestgpt",
    "base": "experiment.base",
}


class LazyCliGroup(click.Group):
    """Load heavy subcommands only when invoked so `init` works with minimal imports."""

    def list_commands(self, ctx):
        commands = set(super().list_commands(ctx))
        commands.update(_LAZY_COMMAND_MODULES)
        return sorted(commands)

    def get_command(self, ctx, name):
        cmd = super().get_command(ctx, name)
        if cmd is not None:
            return cmd
        mod_name = _LAZY_COMMAND_MODULES.get(name)
        if mod_name is None:
            return None
        mod = importlib.import_module(mod_name)
        return mod.main


@click.group(cls=LazyCliGroup, help="VulnBot")
def main():
    ...


@main.command("init")
def init():
    Configs.set_auto_reload(False)
    logger.success(f"Start initializing the project data directory：{Configs.PENTEST_ROOT}")
    Configs.basic_config.make_dirs()
    logger.success("Creating all data directories: Success.")

    Configs.create_all_templates()
    Configs.set_auto_reload(True)
    logger.success("Generating default configuration file: Success.")

    try:
        from utils.session import create_tables

        create_tables()
        logger.success("Initializing database: Success.")
    except Exception as e:
        logger.warning(
            f"Database initialization skipped ({e!r}). "
            "Configuration files were written; set db_config.yaml and run `python cli.py init` again to create tables."
        )


if __name__ == "__main__":
    main()
