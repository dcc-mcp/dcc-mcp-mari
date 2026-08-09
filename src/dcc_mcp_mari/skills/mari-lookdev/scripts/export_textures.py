from dcc_mcp_core.skill import run_main

from dcc_mcp_mari.skill_tools import bridge_main, wait_for_export_files

main = bridge_main(
    "export.run",
    "Mari textures exported.",
    postprocess=wait_for_export_files,
)

if __name__ == "__main__":
    run_main(main)
