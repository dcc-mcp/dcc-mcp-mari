from dcc_mcp_core.skill import run_main

from dcc_mcp_mari.skill_tools import bridge_main

main = bridge_main("shader.remove", "Mari shader removed.")

if __name__ == "__main__":
    run_main(main)
