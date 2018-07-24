
# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

import traverseService as rst
from commonRedfish import *
import RedfishLogo as logo
import html


def wrapTag(string, tag='div', attr=None):
    string = str(string)
    ltag, rtag = '<{}>'.format(tag), '</{}>'.format(tag)
    if attr is not None:
        ltag = '<{} {}>'.format(tag, attr)
    return ltag + string + rtag

def infoBlock(strings, split='<br/>', ffunc=None):
    if isinstance(strings, dict):
        infos = [wrapTag('{}: '.format(y), 'b') + str(x) for y,x in strings.items()]
    else:
        infos = strings
    return split.join([ffunc(*x) for x in enumerate(infos)] if ffunc is not None else infos)

def tableBlock(lines, titles, widths=None, ffunc=None):
    widths = widths if widths is not None else [100 for x in range(len(titles))]
    attrlist = ['style="width:{}%"'.format(str(x)) for x in widths]
    tableHeader = wrapTag(''.join([wrapTag(x,'th',y) for x,y in zip(titles,attrlist)]), 'tr')
    for line in lines:
        tableHeader += wrapTag(''.join([ffunc(cnt, x) if ffunc is not None else wrapTag(x,'td') for cnt, x in enumerate(line)]), 'tr')
    return wrapTag(tableHeader, 'table')


def applySuccessColor(num, entry):
    if num < 4:
        return wrapTag(entry, 'td')
    success_col = str(entry)
    if 'FAIL' in str(success_col).upper():
        entry = '<td class="fail center">' + str(success_col) + '</td>'
    elif 'DEPRECATED' in str(success_col).upper():
        entry = '<td class="warn center">' + str(success_col) + '</td>'
    elif 'PASS' in str(success_col).upper():
        entry = '<td class="pass center">' + str(success_col) + '</td>'
    else:
        entry = '<td class="center">' + str(success_col) + '</td>'
    return entry


def applyInfoSuccessColor(num, entry):
    if 'fail' in entry or 'exception' in entry:
        style = 'class="fail"'
    elif 'warn' in entry:
        style = 'class="warn"'
    else:
        style = None
    return wrapTag(entry, attr=style)


def renderHtml(results, finalCounts, tool_version, startTick, nowTick):
    # Render html
    config = rst.config
    config_str = rst.configToStr()
    rsvLogger = rst.getLogger()
    sysDescription, ConfigURI = (config['systeminfo'], config['targetip'])
    logpath = config['logpath']

    # wrap html
    htmlPage = ''
    htmlStrTop = '<head><title>Conformance Test Summary</title>\
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
        '<tr><th>' \
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

    htmlStr = rst.currentService.metadata.to_html()
    for cnt, item in enumerate(results):
        entry = []
        val = results[item]
        rtime = '(response time: {})'.format(val['rtime'])

        # uri block
        prop_type = val['fulltype']
        if prop_type is not None:
            namespace = getNamespace(prop_type)
            type_name = getType(prop_type)

        infos = [str(val[x]) for x in ['uri', 'samplemapped'] if val[x] not in ['',None]]
        infos.append(rtime)
        infos.append(type_name)
        uriTag = wrapTag(wrapTag(infoBlock(infos, '&ensp;'), 'th', 'class="titlerow bluebg"'), 'tr')
        entry.append(uriTag)

        # info block
        infos = [str(val[x]) for x in ['uri'] if val[x] not in ['',None]]
        infos.append(rtime)
        infos.append(wrapTag('Show Results', attr='class="button warn" onClick="document.getElementById(\'resNum{}\').classList.toggle(\'resultsShow\');"'.format(cnt)))
        buttonTag = wrapTag(infoBlock(infos), 'td', 'class="title" style="width:40%"')

        infos = [str(val[x]) for x in ['context', 'fulltype']]
        infos = {y: x for x,y in zip(infos, ['Schema File: ', 'Resource Type: '])}
        infosTag = wrapTag(infoBlock(infos), 'td', 'class="titlesub log" style="width:30%"')

        success = val['success']
        if success:
            getTag = wrapTag('GET Success', 'td', 'class="pass"')
        else:
            getTag = wrapTag('GET Failure', 'td', 'class="fail"')


        countsTag = wrapTag(infoBlock(val['counts'], split='', ffunc=applyInfoSuccessColor), 'td', 'class="log"')

        rhead = ''.join([buttonTag, infosTag, getTag, countsTag])
        for x in [('tr',), ('table', 'class=titletable'), ('td', 'class=titlerow'), ('tr')]:
            rhead = wrapTag(''.join(rhead), *x)
        entry.append(rhead)

        # actual table
        rows = [[m] + list(val['messages'][m]) for m in val['messages']]
        titles = ['Property Name', 'Value', 'Type', 'Exists', 'Result']
        widths = ['15','30','30','10','15']
        tableHeader = tableBlock(rows, titles, widths, ffunc=applySuccessColor)

        #    lets wrap table and errors and warns into one single column table
        for x in [('td',), ('tr',)]:
            tableHeader = wrapTag(tableHeader, *x)

        # warns and errors
        errors = val['errors']
        if len(errors) == 0:
            errors = 'No errors'
        infos = errors.split('\n')
        errorTags = wrapTag(wrapTag(infoBlock(infos), 'td', 'class="fail log"'), 'tr')

        warns = val['warns']
        if len(warns) == 0:
            warns = 'No warns'
        infos = warns.split('\n')
        warnTags = wrapTag(wrapTag(infoBlock(infos), 'td', 'class="warn log"'), 'tr')

        tableHeader += errorTags
        tableHeader += warnTags
        tableHeader = wrapTag(tableHeader, 'table')
        tableHeader = wrapTag(tableHeader, 'td','class="results" id=\'resNum{}\''.format(cnt))

        entry.append(tableHeader)

        # append
        htmlPage += ''.join([wrapTag(x, 'tr') for x in entry])

    return wrapTag(wrapTag(htmlStrTop + wrapTag(htmlStrBodyHeader + htmlPage, 'table'), 'body'), 'html')



def writeHtml(string, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(string)

