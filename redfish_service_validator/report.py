# Copyright Notice:
# Copyright 2016-2025 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import html as html_mod
import json
from datetime import datetime

from redfish_service_validator import metadata
from redfish_service_validator import redfish_logo
from redfish_service_validator.system_under_test import SystemUnderTest

html_template = """
<html>
  <head>
    <title>Redfish Service Validator Test Summary</title>
    <style>
      .pass {{background-color:#99EE99}}
      .fail {{background-color:#EE9999}}
      .warn {{background-color:#EEEE99}}
      .bluebg {{background-color:#BDD6EE}}
      .button {{padding: 12px; display: inline-block; border:1px solid black;}}
      .center {{text-align:center;}}
      .left {{text-align:left;}}
      .log {{text-align:left; white-space:pre-wrap; word-wrap:break-word;
             font-size:smaller}}
      .title {{background-color:#DDDDDD; border: 1pt solid; font-height: 30px;
               padding: 8px}}
      .titlesub {{padding: 8px}}
      .titlerow {{border: 2pt solid}}
      .headingrow {{border: 2pt solid; text-align:left;
                    background-color:beige;}}
      .results {{transition: visibility 0s, opacity 0.5s linear; display: none;
                 opacity: 0}}
      .resultsShow {{display: block; opacity: 1}}
      body {{background-color:lightgrey; border: 1pt solid; text-align:center;
             margin-left:auto; margin-right:auto}}
      th {{text-align:center; background-color:beige; border: 1pt solid}}
      td {{text-align:left; background-color:white; border: 1pt solid;
           word-wrap:break-word;}}
      table {{width:90%; margin: 0px auto; table-layout:fixed;}}
      .titletable {{width:100%}}
    </style>
  </head>
  <table>
    <tr>
      <th>
        <h2>##### Redfish Service Validator Test Report #####</h2>
        <h4><img align=\"center\" alt=\"DMTF Redfish Logo\" height=\"203\"
            width=\"288\" src=\"data:image/gif;base64,{}\"></h4>
        <h4><a href=\"https://github.com/DMTF/Redfish-Service-Validator\">
            https://github.com/DMTF/Redfish-Service-Validator</a></h4>
        Tool Version: {}<br/>
        {}<br/><br/>
        This tool is provided and maintained by the DMTF. For feedback, please
        open issues<br/> in the tool's Github repository:
        <a href=\"https://github.com/DMTF/Redfish-Service-Validator/issues\">
            https://github.com/DMTF/Redfish-Service-Validator/issues</a><br/>
      </th>
    </tr>
    <tr>
      <th>
        System: {}/redfish/v1/, User: {}, Password: {}<br/>
        Product: {}<br/>
        Manufacturer: {}, Model: {}, Firmware version: {}<br/>
      </th>
    </tr>
    <tr>
      <td>
        <center><b>Results Summary</b></center>
        <center>Pass: {}, Warning: {}, Fail: {}, Not tested: {}</center>
      </td>
    </tr>
    {}
  </table>
</html>
"""

results_header_html = """
  <tr>
    <td class=titlerow>
      <table class=titletable>
        <tr>
          <td class="titlerow bluebg"><b><div>{}</div><div>{}</div></b></td>
          <td style="width:20%">{}</td>
          <td class="title" style="width:20%"><div class="button bluebg" onClick="document.getElementById('{}').classList.remove('resultsShow'); document.getElementById('{}').classList.toggle('resultsShow');">Show Results</div><div class="button bluebg" onClick="document.getElementById('{}').classList.toggle('resultsShow'); document.getElementById('{}').classList.add('resultsShow');">Show Payload</div></td>
        </tr>
      </table>
    </td>
  </tr>
"""

results_detailed_html = """
  <tr>
    <td class="results" id='{}'>
      <table>
        <tr>
          <td>
            <table>
              <tr>
                <th style="width:30%">Name</th><th>Value</th><th style="width:10%">Result</th>
              </tr>
              {}
            </table>
          </td>
        </tr>
        <td class="results log" id='{}'>{}</td>
      </table>
    </td>
  </tr>
"""


def html_report(sut: SystemUnderTest, report_dir, time, tool_version):
    """
    Creates the HTML report for the system under test

    Args:
        sut: The system under test
        report_dir: The directory for the report
        time: The time the tests finished
        tool_version: The version of the tool

    Returns:
        The path to the HTML report
    """
    file = report_dir / datetime.strftime(time, "RedfishServiceValidatorReport_%m_%d_%Y_%H%M%S.html")
    html = ""
    uris = sorted(list(sut._resources.keys()), key=str.lower)
    for index, uri in enumerate(uris):
        if not sut._resources[uri]["Validated"]:
            # Skip resources we didn't test
            # They might just be cached for reference link checks
            continue

        # Get the type info for the URI
        try:
            resource_type = sut._resources[uri]["Response"].dict["@odata.type"][1:].split(".")[0]
            try:
                resource_version = metadata.get_version(sut._resources[uri]["Response"].dict["@odata.type"])
                resource_version_str = "v{}.{}.{}".format(resource_version[0], resource_version[1], resource_version[2])
                resource_type += ", {}".format(resource_version_str)
            except:
                pass
        except:
            resource_type = "Unknown Resource Type"

        # Build the results summary for the URI
        uri_summary = "<div>Pass: {}</div>".format(sut._resources[uri]["Pass"])
        if sut._resources[uri]["Warn"]:
            uri_summary += "<div class=\"warn\">Warning: {}</div>".format(sut._resources[uri]["Warn"])
        if sut._resources[uri]["Fail"]:
            uri_summary += "<div class=\"fail\">Failure: {}</div>".format(sut._resources[uri]["Fail"])

        # Insert the URI results header
        results_id = "results{}".format(index)
        payload_id = "payload{}".format(index)
        html += results_header_html.format(uri, resource_type, uri_summary, payload_id, results_id, payload_id, results_id)

        # Insert the URI results details
        results_str = ""
        props = sorted(list(sut._resources[uri]["Results"]), key=str.lower)
        for prop in props:
            if prop == "":
                prop_str = "-"
            else:
                prop_str = prop[1:]
            result_class = ""
            value_str = "<div>{}</div>".format(sut._resources[uri]["Results"][prop]["Value"])
            if sut._resources[uri]["Results"][prop]["Result"] == "PASS":
                result_class = 'class="pass"'
            elif sut._resources[uri]["Results"][prop]["Result"] == "WARN":
                result_class = 'class="warn"'
                value_str += "<div class=\"warn\">{}</div>".format(sut._resources[uri]["Results"][prop]["Message"])
            elif sut._resources[uri]["Results"][prop]["Result"] == "FAIL":
                result_class = 'class="fail"'
                value_str += "<div class=\"fail\">{}</div>".format(sut._resources[uri]["Results"][prop]["Message"])
            results_str += "<tr><td>{}</td><td>{}</td><td {}>{}</td></tr>".format(prop_str, value_str, result_class, sut._resources[uri]["Results"][prop]["Result"])
        try:
            payload_str = json.dumps( sut._resources[uri]["Response"].dict, sort_keys=True, indent=4, separators=(",", ": "))
        except:
            payload_str = "Malformed JSON"
        html += results_detailed_html.format(results_id, results_str, payload_id, payload_str)

    with open(str(file), "w", encoding="utf-8") as fd:
        fd.write(
            html_template.format(
                redfish_logo.logo,
                tool_version,
                time.strftime("%c"),
                sut.rhost,
                sut.username,
                "********",
                sut.product,
                sut.manufacturer,
                sut.model,
                sut.firmware_version,
                sut.pass_count,
                sut.warn_count,
                sut.fail_count,
                sut.skip_count,
                html,
            )
        )
    return file
