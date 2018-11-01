# Copyright Notice:
# Copyright 2016-2018 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

from commonRedfish import getNamespace, getType
import RedfishLogo as logo
from types import SimpleNamespace
import html
import json


# hack in tagnames into module namespace
tag = SimpleNamespace(**{tagName: lambda string, attr=None, tag=tagName: wrapTag(string, tag=tag, attr=attr)\
    for tagName in ['tr', 'td', 'th', 'div', 'b', 'table', 'body', 'head', 'summary']})


def wrapTag(string, tag='div', attr=None):
    string = str(string)
    ltag, rtag = '<{}>'.format(tag), '</{}>'.format(tag)
    if attr is not None:
        ltag = '<{} {}>'.format(tag, attr)
    return ltag + string + rtag


def infoBlock(strings, split='<br/>', ffunc=None, sort=True):
    if isinstance(strings, dict):
        infos = [tag.b('{}: '.format(y)) + str(x) for y, x in (sorted(strings.items()) if sort else strings.items())]
    else:
        infos = strings
    return split.join([ffunc(*x) for x in enumerate(infos)] if ffunc is not None else infos)


def tableBlock(lines, titles, widths=None, ffunc=None):
    widths = widths if widths is not None else [100 for x in range(len(titles))]
    attrlist = ['style="width:{}%"'.format(str(x)) for x in widths]
    tableHeader = tag.tr(''.join([tag.th(x, y) for x, y in zip(titles,attrlist)]))
    for line in lines:
        tableHeader += tag.tr(''.join([ffunc(cnt, x) if ffunc is not None else tag.td(x) for cnt, x in enumerate(line)]))
    return tag.table(tableHeader)


def applySuccessColor(num, entry):
    if num < 4:
        return wrapTag(entry, 'td')
    success_col = str(entry)
    if 'FAIL' in str(success_col).upper():
        entry = '<td class="fail center">' + str(success_col) + '</td>'
    elif str(success_col).upper() in ['DEPRECATED', 'INVALID']:
        entry = '<td class="warn center">' + str(success_col) + '</td>'
    elif 'PASS' in str(success_col).upper():
        entry = '<td class="pass center">' + str(success_col) + '</td>'
    else:
        entry = '<td class="center">' + str(success_col) + '</td>'
    return entry


def applyInfoSuccessColor(num, entry):
    if 'fail' in entry or 'exception' in entry or 'problem' in entry:
        style = 'class="fail"'
    elif 'warn' in entry or 'invalid' in entry:
        style = 'class="warn"'
    else:
        style = None
    return tag.div(entry, attr=style)


def renderHtml(results, finalCounts, tool_version, startTick, nowTick, service):
    # Render html
    config = service.config
    config_str = ', '.join(sorted(list(config.keys() - set(['systeminfo', 'targetip', 'password', 'description']))))
    sysDescription, ConfigURI = (config['systeminfo'], config['targetip'])
    logpath = config['logpath']

    # wrap html
    htmlPage = ''
    htmlStrTop = '<head><title>Conformance Test Summary</title>\
            <style>\
            .pass {background-color:#99EE99}\
            .column {\
                float: left;\
                width: 50%;\
            }\
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
            td {text-align:left; background-color:white; border: 1pt solid; word-wrap:break-word; overflow:hidden;}\
            table {width:90%; margin: 0px auto; table-layout:fixed;}\
            .titletable {width:100%}\
            </style>\
            </head>'
    htmlStrBodyHeader = ''
    # Logo and logname
    infos = [wrapTag('##### Redfish Conformance Test Report #####', 'h2')]
    infos.append(wrapTag('<img align="center" alt="DMTF Redfish Logo" height="203" width="288"'
                         'src="data:image/gif;base64,' + logo.logo + '">', 'h4'))
    infos.append('<h4><a href="https://github.com/DMTF/Redfish-Service-Validator">'
                 'https://github.com/DMTF/Redfish-Service-Validator</a></h4>')
    infos.append('Tool Version: {}'.format(tool_version))
    infos.append(startTick.strftime('%c'))
    infos.append('(Run time: {})'.format(
        str(nowTick - startTick).rsplit('.', 1)[0]))
    infos.append('<h4>This tool is provided and maintained by the DMTF. '
                 'For feedback, please open issues<br>in the tool\'s Github repository: '
                 '<a href="https://github.com/DMTF/Redfish-Service-Validator/issues">'
                 'https://github.com/DMTF/Redfish-Service-Validator/issues</a></h4>')

    htmlStrBodyHeader += tag.tr(tag.th(infoBlock(infos)))

    infos = {'System': ConfigURI, 'Description': sysDescription}
    htmlStrBodyHeader += tag.tr(tag.th(infoBlock(infos)))

    infos = {x: config[x] for x in config if x not in ['systeminfo', 'targetip', 'password', 'description']}
    infos_left, infos_right = dict(), dict()
    for key in sorted(infos.keys()):
        if len(infos_left) <= len(infos_right):
            infos_left[key] = infos[key]
        else:
            infos_right[key] = infos[key]

    block = tag.td(tag.div(infoBlock(infos_left), 'class=\'column log\'') \
            + tag.div(infoBlock(infos_right), 'class=\'column log\''), 'id=\'resNumConfig\' class=\'results resultsShow\'')

    htmlStrTotal = '<div>Final counts: '
    for countType in sorted(finalCounts.keys()):
        if finalCounts.get(countType) == 0:
            continue
        htmlStrTotal += '{p}: {q},   '.format(p=countType, q=finalCounts.get(countType, 0))
    htmlStrTotal += '</div>'
    htmlStrTotal += '<div class="button warn" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results resultsShow\'};">Expand All</div>'
    htmlStrTotal += '<div class="button fail" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results\'};">Collapse All</div>'
    htmlStrTotal += tag.div('Show Config', attr='class="button pass" onClick="document.getElementById(\'resNumConfig\').classList.toggle(\'resultsShow\');"')

    htmlStrBodyHeader += tag.tr(tag.td(htmlStrTotal))
    htmlStrBodyHeader += tag.tr(block)


    htmlPage = service.metadata.to_html()
    for cnt, item in enumerate(results):
        entry = []
        val = results[item]
        rtime = '(response time: {})'.format(val['rtime'])
        rcode = '({})'.format(val['rcode'])
        payload = val['payload']

        # uri block
        prop_type = val['fulltype']
        if prop_type is not None:
            namespace = getNamespace(prop_type)
            type_name = getType(prop_type)

        infos = [str(val.get(x)) for x in ['uri', 'samplemapped'] if val.get(x) not in ['',None]]
        infos.append(rtime)
        infos.append(type_name)
        uriTag = tag.tr(tag.th(infoBlock(infos, '&ensp;'), 'class="titlerow bluebg"'))
        entry.append(uriTag)

        # info block
        infos = [str(val.get(x)) for x in ['uri'] if val.get(x) not in ['',None]]
        infos.append(rtime)
        infos.append(tag.div('Show Results', attr='class="button warn"\
                onClick="document.getElementById(\'payload{}\').classList.remove(\'resultsShow\');\
                document.getElementById(\'resNum{}\').classList.toggle(\'resultsShow\');\
                document.getElementById(\'payload{}\').scrollIntoView();"'.format(cnt, cnt, cnt)))
        infos.append(tag.div('Show Payload', attr='class="button pass"\
                onClick="document.getElementById(\'payload{}\').classList.toggle(\'resultsShow\');\
                document.getElementById(\'resNum{}\').classList.add(\'resultsShow\');\
                document.getElementById(\'payload{}\').scrollIntoView();"'.format(cnt, cnt, cnt)))
        buttonTag = tag.td(infoBlock(infos), 'class="title" style="width:30%"')

        infos = [str(val.get(x)) for x in ['context', 'origin', 'fulltype']]
        infos = {y: x for x, y in zip(infos, ['Context', 'File Origin', 'Resource Type'])}
        infosTag = tag.td(infoBlock(infos), 'class="titlesub log" style="width:40%"')

        success = val['success']
        if success:
            getTag = tag.td('GET Success {}'.format(rcode), 'class="pass"')
        else:
            getTag = tag.td('GET Failure {}'.format(rcode), 'class="fail"')

        countsTag = tag.td(infoBlock(val['counts'], split='', ffunc=applyInfoSuccessColor), 'class="log"')

        rhead = ''.join([buttonTag, infosTag, getTag, countsTag])
        for x in [('tr',), ('table', 'class=titletable'), ('td', 'class=titlerow'), ('tr')]:
            rhead = wrapTag(''.join(rhead), *x)
        entry.append(rhead)

        # actual table
        rows = [[m] + list(val['messages'][m]) for m in val['messages']]
        titles = ['Property Name', 'Value', 'Type', 'Exists', 'Result']
        widths = ['15', '30', '30', '10', '15']
        tableHeader = tableBlock(rows, titles, widths, ffunc=applySuccessColor)

        #    lets wrap table and errors and warns into one single column table
        tableHeader = tag.tr(tag.td((tableHeader)))

        # warns and errors
        errors = val['errors']
        if len(errors) == 0:
            errors = 'No errors'
        infos = errors.split('\n')
        errorTags = tag.tr(tag.td(infoBlock(infos), 'class="fail log"'))

        warns = val['warns']
        if len(warns) == 0:
            warns = 'No warns'
        infos = warns.split('\n')
        warnTags = tag.tr(tag.td(infoBlock(infos), 'class="warn log"'))

        payloadTag = tag.td(json.dumps(payload, indent=4, sort_keys=True), 'id=\'payload{}\' class=\'results log\''.format(cnt))

        tableHeader += errorTags
        tableHeader += warnTags
        tableHeader += payloadTag
        tableHeader = tag.table(tableHeader)
        tableHeader = tag.td(tableHeader, 'class="results" id=\'resNum{}\''.format(cnt))

        entry.append(tableHeader)



        # append
        htmlPage += ''.join([tag.tr(x) for x in entry])

    return wrapTag(wrapTag(htmlStrTop + wrapTag(htmlStrBodyHeader + htmlPage, 'table'), 'body'), 'html')


def writeHtml(string, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(string)

