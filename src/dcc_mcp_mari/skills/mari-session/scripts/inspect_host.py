from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_mari.bridge import get_bridge


@skill_entry
def main(**_kwargs):
    result = get_bridge().call("mari.inspect_project")
    return skill_success("Mari project inspected.", project=result)


if __name__ == "__main__":
    run_main(main)
