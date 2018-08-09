
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


# hack in tagnames into module namespace
for tagName in ['tr', 'td', 'th', 'div', 'b', 'table', 'body', 'head']:
    globals()[tagName] = lambda string, attr=None, tag=tagName: wrapTag(string, tag=tag, attr=attr)


def infoBlock(strings, split='<br/>', ffunc=None, sort=True):
    if isinstance(strings, dict):
        infos = [b('{}: '.format(y)) + str(x) for y,x in (sorted(strings.items()) if sort else strings.items())]
    else:
        infos = strings
    return split.join([ffunc(*x) for x in enumerate(infos)] if ffunc is not None else infos)


def tableBlock(lines, titles, widths=None, ffunc=None):
    widths = widths if widths is not None else [100 for x in range(len(titles))]
    attrlist = ['style="width:{}%"'.format(str(x)) for x in widths]
    tableHeader = tr(''.join([th(x,y) for x,y in zip(titles,attrlist)]))
    for line in lines:
        tableHeader += tr(''.join([ffunc(cnt, x) if ffunc is not None else td(x) for cnt, x in enumerate(line)]))
    return table(tableHeader)


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
    return div(entry, attr=style)


def renderHtml(results, finalCounts, tool_version, startTick, nowTick):
    # Render html
    config = rst.config
    config_str = ', '.join(sorted(list(config.keys() - set(['systeminfo', 'targetip', 'password', 'description']))))
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
        '<h4>System: <a href="' + ConfigURI + '">' + ConfigURI + '</a> Description: ' + sysDescription + '</h4>' \
        '</th></tr>' \
        '<tr><th>' \
        '<h4>Configuration:</h4>' \
        '<h4>' + str(config_str.replace('\n', '<br>')) + '</h4>' \
        '</th></tr>' \
        ''
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
        str(nowTick-startTick).rsplit('.', 1)[0]))
    infos.append('<h4>This tool is provided and maintained by the DMTF. '
                 'For feedback, please open issues<br>in the tool\'s Github repository: '
                 '<a href="https://github.com/DMTF/Redfish-Service-Validator/issues">'
                 'https://github.com/DMTF/Redfish-Service-Validator/issues</a></h4>')

    htmlStrBodyHeader += tr(th(infoBlock(infos)))

    infos = {'System': ConfigURI, 'Description': sysDescription}
    htmlStrBodyHeader += tr(th(infoBlock(infos)))

    infos = {x: config[x] for x in config if x not in ['systeminfo', 'targetip', 'password', 'description']}
    block = tr(th(infoBlock(infos, '|||')))
    for num, block in enumerate(block.split('|||'), 1):
        sep = '<br/>' if num % 4 == 0 else ',&ensp;'
        sep = '' if num == len(infos) else sep
        htmlStrBodyHeader += block + sep

    htmlStrTotal = '<div>Final counts: '
    for countType in sorted(finalCounts.keys()):
        if finalCounts.get(countType) == 0:
            continue
        htmlStrTotal += '{p}: {q},   '.format(p=countType, q=finalCounts.get(countType, 0))
    htmlStrTotal += '</div><div class="button warn" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results resultsShow\'};">Expand All</div>'
    htmlStrTotal += '</div><div class="button fail" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].className = \'results\'};">Collapse All</div>'

    htmlStrBodyHeader += tr(td(htmlStrTotal))

    htmlPage = rst.currentService.metadata.to_html()
    for cnt, item in enumerate(results):
        entry = []
        val = results[item]
        rtime = '(response time: {})'.format(val['rtime'])

        # uri block
        prop_type = val['fulltype']
        if prop_type is not None:
            namespace = getNamespace(prop_type)
            type_name = getType(prop_type)

        infos = [str(val.get(x)) for x in ['uri', 'samplemapped'] if val.get(x) not in ['',None]]
        infos.append(rtime)
        infos.append(type_name)
        uriTag = tr(th(infoBlock(infos, '&ensp;'), 'class="titlerow bluebg"'))
        entry.append(uriTag)

        # info block
        infos = [str(val.get(x)) for x in ['uri'] if val.get(x) not in ['',None]]
        infos.append(rtime)
        infos.append(div('Show Results', attr='class="button warn" onClick="document.getElementById(\'resNum{}\').classList.toggle(\'resultsShow\');"'.format(cnt)))
        buttonTag = td(infoBlock(infos), 'class="title" style="width:30%"')

        infos = [str(val.get(x)) for x in ['context', 'origin', 'fulltype']]
        infos = {y: x for x,y in zip(infos, ['Context', 'File Origin', 'Resource Type'])}
        infosTag = td(infoBlock(infos), 'class="titlesub log" style="width:40%"')

        success = val['success']
        if success:
            getTag = td('GET Success', 'class="pass"')
        else:
            getTag = td('GET Failure', 'class="fail"')


        countsTag = td(infoBlock(val['counts'], split='', ffunc=applyInfoSuccessColor), 'class="log"')

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
        tableHeader = tr(td((tableHeader)))

        # warns and errors
        errors = val['errors']
        if len(errors) == 0:
            errors = 'No errors'
        infos = errors.split('\n')
        errorTags = tr(td(infoBlock(infos), 'class="fail log"'))

        warns = val['warns']
        if len(warns) == 0:
            warns = 'No warns'
        infos = warns.split('\n')
        warnTags = tr(td(infoBlock(infos), 'class="warn log"'))

        tableHeader += errorTags
        tableHeader += warnTags
        tableHeader = table(tableHeader)
        tableHeader = td(tableHeader, 'class="results" id=\'resNum{}\''.format(cnt))

        entry.append(tableHeader)

        # append
        htmlPage += ''.join([tr(x) for x in entry])

    return wrapTag(wrapTag(htmlStrTop + wrapTag(htmlStrBodyHeader + htmlPage, 'table'), 'body'), 'html')



def writeHtml(string, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(string)

