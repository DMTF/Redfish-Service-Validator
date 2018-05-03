
# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import traverseService as rst
import RedfishLogo as logo
import html

def resultTupleToDict():
    pass 

def renderHtml(results, finalCounts, tool_version, startTick, nowTick):
    # Render html
    config = rst.config
    config_str = rst.configToStr()
    rsvLogger = rst.getLogger()
    sysDescription, ConfigURI = (config['systeminfo'], config['targetip'])
    logpath = config['logpath']

    htmlStrTop = '<html><head><title>Conformance Test Summary</title>\
            <style>\
            .pass {background-color:#99EE99}\
            .fail {background-color:#EE9999}\
            .warn {background-color:#EEEE99}\
            .bluebg {background-color:#BDD6EE}\
            .button {padding: 12px; display: inline-block}\
            .center {text-align:center;}\
            .log {text-align:left; white-space:pre-wrap; word-wrap:break-word; font-size:smaller}\
            .title {background-color:#DDDDDD; border: 1pt solid; font-height: 30px; padding: 8px}\
            .titlesub {padding: 8px}\
            .titlerow {border: 2pt solid}\
            .results {transition: visibility 0s, opacity 0.5s linear; display: none; opacity: 0}\
            .resultsShow {display: block; opacity: 1}\
            body {background-color:lightgrey; border: 1pt solid; text-align:center; margin-left:auto; margin-right:auto}\
            th {text-align:center; background-color:beige; border: 1pt solid}\
            td {text-align:left; background-color:white; border: 1pt solid; word-wrap:break-word;}\
            table {width:90%; margin: 0px auto; table-layout:fixed;}\
            .titletable {width:100%}\
            </style>\
            </head>'

    htmlStrBodyHeader = \
        '<body><table><tr><th>' \
        '<h2>##### Redfish Conformance Test Report #####</h2>' \
        '<br>' \
        '<h4><img align="center" alt="DMTF Redfish Logo" height="203" width="288"' \
        'src="data:image/gif;base64,' + logo.logo + '"></h4>' \
        '<br>' \
        '<h4><a href="https://github.com/DMTF/Redfish-Service-Validator">' \
        'https://github.com/DMTF/Redfish-Service-Validator</a>' \
        '<br>Tool Version: ' + tool_version + \
        '<br>' + startTick.strftime('%c') + \
        '<br>(Run time: ' + str(nowTick-startTick).rsplit('.', 1)[0] + ')' \
        '' \
        '<h4>This tool is provided and maintained by the DMTF. ' \
        'For feedback, please open issues<br>in the tool\'s Github repository: ' \
        '<a href="https://github.com/DMTF/Redfish-Service-Validator/issues">' \
        'https://github.com/DMTF/Redfish-Service-Validator/issues</a></h4>' \
        '</th></tr>' \
        '<tr><th>' \
        '<h4>System: <a href="' + ConfigURI + '">' + ConfigURI + '</a> Description: ' + sysDescription + '</h4>' \
        '</th></tr>' \
        '<tr><th>' \
        '<h4>Configuration:</h4>' \
        '<h4>' + str(config_str.replace('\n', '<br>')) + '</h4>' \
        '</th></tr>' \
        ''

    htmlStr = rst.metadata.to_html()

    rsvLogger.info(len(results))
    for cnt, item in enumerate(results):
        type_name = ''
        prop_type = results[item]['fulltype']
        if prop_type is not None:
            namespace = prop_type.replace('#', '').rsplit('.', 1)[0]
            type_name = prop_type.replace('#', '').rsplit('.', 1)[-1]
            if '.' in namespace:
                type_name += ' ' + namespace.split('.', 1)[-1]
        htmlStr += '<tr><th class="titlerow bluebg"><b>{}</b> ({})</th></tr>'.format(results[item]['uri'], type_name)
        htmlStr += '<tr><td class="titlerow"><table class="titletable"><tr>'
        htmlStr += '<td class="title" style="width:40%"><div>{}</div>\
                <div class="button warn" onClick="document.getElementById(\'resNum{}\').classList.toggle(\'resultsShow\');">Show results</div>\
                </td>'.format(results[item]['uri'], cnt, cnt)
        htmlStr += '<td class="titlesub log" style="width:30%"><div><b>Schema File:</b> {}</div><div><b>Resource Type:</b> {}</div></td>'.format(results[item]['context'], type_name)
        htmlStr += '<td style="width:10%"' + \
            ('class="pass"> GET Success' if results[item]['success'] else 'class="fail"> GET Failure') + '</td>'
        htmlStr += '<td style="width:10%">'

        innerCounts = results[item]['counts']

        for countType in sorted(innerCounts.keys()):
            if 'problem' in countType or 'fail' in countType or 'exception' in countType:
                rsvLogger.error('{} {} errors in {}'.format(innerCounts[countType], countType, str(results[item]['uri']).split(' ')[0]))  # Printout FORMAT
            innerCounts[countType] += 0
            if 'fail' in countType or 'exception' in countType:
                style = 'class="fail log"'
            elif 'warn' in countType:
                style = 'class="warn log"'
            else:
                style = 'class=log'
            htmlStr += '<div {style}>{p}: {q}</div>'.format(
                    p=countType,
                    q=innerCounts.get(countType, 0),
                    style=style)
        htmlStr += '</td></tr>'
        htmlStr += '</table></td></tr>'
        htmlStr += '<tr><td class="results" id=\'resNum{}\'><table><tr><td><table><tr><th style="width:15%">Property Name</th> <th>Value</th> <th>Type</th> <th style="width:10%">Exists?</th> <th style="width:10%">Result</th> <tr>'.format(cnt)
        if results[item]['messages'] is not None:
            messages = results[item]['messages']
            for i in messages:
                htmlStr += '<tr>'
                htmlStr += '<td>' + str(i) + '</td>'
                for j in messages[i][:-1]:
                    htmlStr += '<td >' + str(j) + '</td>'
                # only color-code the last ("Success") column
                success_col = messages[i][-1]
                if 'FAIL' in str(success_col).upper():
                    htmlStr += '<td class="fail center">' + str(success_col) + '</td>'
                elif 'DEPRECATED' in str(success_col).upper():
                    htmlStr += '<td class="warn center">' + str(success_col) + '</td>'
                elif 'PASS' in str(success_col).upper():
                    htmlStr += '<td class="pass center">' + str(success_col) + '</td>'
                else:
                    htmlStr += '<td class="center">' + str(success_col) + '</td>'
                htmlStr += '</tr>'
        htmlStr += '</table></td></tr>'
        if results[item]['errors'] is not None:
            htmlStr += '<tr><td class="fail log">' + html.escape(results[item]['errors'].getvalue()).replace('\n', '<br />') + '</td></tr>'
            results[item]['errors'].close()
        if results[item]['warns'] is not None:
            htmlStr += '<tr><td class="warn log">' + html.escape(results[item]['warns'].getvalue()).replace('\n', '<br />') + '</td></tr>'
            results[item]['warns'].close()
        htmlStr += '<tr><td>---</td></tr></table></td></tr>'

    htmlStr += '</table></body></html>'

    htmlStrTotal = '<tr><td><div>Final counts: '
    for countType in sorted(finalCounts.keys()):
        htmlStrTotal += '{p}: {q},   '.format(p=countType, q=finalCounts.get(countType, 0))
    htmlStrTotal += '</div><div class="button warn" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results resultsShow\'};">Expand All</div>'
    htmlStrTotal += '</div><div class="button fail" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results\'};">Collapse All</div>'

    htmlPage = htmlStrTop + htmlStrBodyHeader + htmlStrTotal + htmlStr

    return htmlPage


def writeHtml(string, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(string)

