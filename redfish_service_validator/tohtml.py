# Copyright Notice:
# Copyright 2016-2024 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

if __name__ != '__main__':
    from redfish_service_validator.helper import getType
else:
    import argparse
    from bs4 import BeautifulSoup
    import os, csv
import redfish_service_validator.RedfishLogo as logo
from redfish_service_validator.helper import LOG_ENTRY
from types import SimpleNamespace
from collections import Counter
import json
import re

# hack in tagnames into module namespace
tag = SimpleNamespace(**{tagName: lambda string, attr=None, tag=tagName: wrapTag(string, tag=tag, attr=attr)\
    for tagName in ['tr', 'td', 'th', 'div', 'b', 'table', 'body', 'head', 'summary']})

def count_errors(results):
    error_lines = []
    finalCounts = Counter()
    for item in results:
        innerCounts = results[item]['counts']

        # detect if there are error messages for this resource, but no failure counts; if so, add one to the innerCounts
        counters_all_pass = True
        for countType in sorted(innerCounts.keys()):
            if innerCounts.get(countType) == 0:
                continue
            if re.search(r"^error|problem|fail|bad|exception|err[.]", countType):
                counters_all_pass = False
                error_lines.append('{} {} errors in {}'.format(innerCounts[countType], countType, results[item]['uri']))
            innerCounts[countType] += 0
        error_messages_present = False
        if results[item]['errors'] is not None and len(results[item]['errors']) > 0:
            error_messages_present = True
        if results[item]['warns'] is not None and len(results[item]['warns']) > 0:
            if "warningPresent" in innerCounts: innerCounts['warnings'] += 1
            innerCounts['warningPresent'] = 1
        if counters_all_pass and error_messages_present:
            innerCounts['failErrorPresent'] = 1
            error_lines.append('Error message present in {}'.format(results[item]['uri']))

        finalCounts.update(innerCounts)
    return error_lines, finalCounts

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
    if any(x.upper() in str(success_col).upper() for x in ['FAIL', 'errorExcerpt']):
        entry = '<td class="fail center">' + str(success_col) + '</td>'
    elif str(success_col).upper() in ['DEPRECATED', 'INVALID', 'WARN']:
        entry = '<td class="warn center">' + str(success_col) + '</td>'
    elif any(x in str(success_col).upper() for x in ['DEPRECATED', 'INVALID', 'WARN']):
        entry = '<td class="warn center">' + str(success_col) + '</td>'
    elif 'PASS' in str(success_col).upper():
        entry = '<td class="pass center">' + str(success_col) + '</td>'
    else:
        entry = '<td class="center">' + str(success_col) + '</td>'
    return entry


def applyInfoSuccessColor(num, entry):
    if any(x in entry for x in ['fail', 'exception', 'error', 'problem', 'err']):
        style = 'class="fail"'
    elif 'warn' in entry or 'invalid' in entry:
        style = 'class="warn"'
    else:
        style = None
    return tag.div(entry, attr=style)


def renderHtml(results, tool_version, startTick, nowTick, service):
    # Render html
    config = service.config
    sysDescription, ConfigURI = (config['description'], config['ip'])
    error_lines, finalCounts = count_errors(results)
    if service.metadata is not None:
        finalCounts.update(service.metadata.get_counter())

    # wrap html
    htmlPage = ''
    htmlStrTop = '<head><title>Conformance Test Summary</title>\
            <style>\
            .pass {background-color:#99EE99}\
            .column {\
                float: left;\
                width: 45%;\
            }\
            .fail {background-color:#EE9999}\
            .warn {background-color:#EEEE99}\
            .bluebg {background-color:#BDD6EE}\
            .button {padding: 12px; display: inline-block}\
            .center {text-align:center;}\
            .log {text-align:left; white-space:pre-wrap; word-wrap:break-word; font-size:smaller; padding: 6px}\
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

    infos = {x: config[x] for x in config if x not in ['systeminfo', 'ip', 'password', 'description']}
    infos_left, infos_right = dict(), dict()
    for key in sorted(infos.keys()):
        if len(infos_left) <= len(infos_right):
            infos_left[key] = infos[key]
        else:
            infos_right[key] = infos[key]

    block = tag.td(tag.div(infoBlock(infos_left), 'class=\'column log\'') \
            + tag.div(infoBlock(infos_right), 'class=\'column log\''), 'id=\'resNumConfig\' class=\'results resultsShow\'')

    htmlButtons = '<div class="button warn" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].classList.add(\'resultsShow\')};">Expand All</div>'
    htmlButtons += '<div class="button fail" onClick="arr = document.getElementsByClassName(\'results\'); for (var i = 0; i < arr.length; i++){arr[i].classList.remove(\'resultsShow\')};">Collapse All</div>'
    htmlButtons += tag.div('Toggle Config', attr='class="button pass" onClick="document.getElementById(\'resNumConfig\').classList.toggle(\'resultsShow\');"')

    htmlStrBodyHeader += tag.tr(tag.th(htmlButtons))
    htmlStrBodyHeader += tag.tr(tag.th('Test Summary'))

    infos = {'System': ConfigURI, 'Description': sysDescription}
    htmlStrBodyHeader += tag.tr(tag.th(infoBlock(infos)))

    errors = error_lines
    if len(errors) == 0:
        errors = ['No errors located.']
    errorTags = tag.td(infoBlock(errors), 'class="log"')

    infos_left, infos_right = dict(), dict()
    for key in sorted(finalCounts.keys()):
        if finalCounts.get(key) == 0:
            continue
        if len(infos_left) <= len(infos_right):
            infos_left[key] = finalCounts[key]
        else:
            infos_right[key] = finalCounts[key]

    htmlStrCounts = (tag.div(infoBlock(infos_left), 'class=\'column log\'') + tag.div(infoBlock(infos_right), 'class=\'column log\''))

    htmlStrBodyHeader += tag.tr(tag.td(htmlStrCounts))

    htmlStrBodyHeader += tag.tr(errorTags)

    htmlStrBodyHeader += tag.tr(block)


    if service.metadata is not None:
        htmlPage = service.metadata.to_html()
    for cnt, item in enumerate(results):
        entry = []
        val = results[item]
        rtime = '(response time: {})'.format(val['rtime'])
        rcode = '({})'.format(val['rcode'])
        payload = val.get('payload', {})

        # uri block
        prop_type = val['fulltype']
        if prop_type is not None:
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
                document.getElementById(\'resNum{}\').classList.toggle(\'resultsShow\');"'.format(cnt, cnt)))
        infos.append(tag.div('Show Payload', attr='class="button pass"\
                onClick="document.getElementById(\'payload{}\').classList.toggle(\'resultsShow\');\
                document.getElementById(\'resNum{}\').classList.add(\'resultsShow\');"'.format(cnt, cnt)))
        buttonTag = tag.td(infoBlock(infos), 'class="title" style="width:30%"')

        infos = [str(val.get(x)) for x in ['context', 'origin', 'fulltype']]
        infos = {y: x for x, y in zip(infos, ['Context', 'File Origin', 'Resource Type'])}
        infosTag = tag.td(infoBlock(infos), 'class="titlesub log" style="width:40%"')

        success = val['success']
        if success:
            getTag = tag.td('GET Success HTTP Code {}'.format(rcode), 'class="pass"')
        else:
            getTag = tag.td('GET Failure HTTP Code {}'.format(rcode), 'class="fail"')

        countsTag = tag.td(infoBlock(val['counts'], split='', ffunc=applyInfoSuccessColor), 'class="log"')

        rhead = ''.join([buttonTag, infosTag, getTag, countsTag])
        for x in [('tr',), ('table', 'class=titletable'), ('td', 'class=titlerow'), ('tr')]:
            rhead = wrapTag(''.join(rhead), *x)
        entry.append(rhead)

        # actual table

        rows = [list([str(vars(m)[x]) for x in LOG_ENTRY]) for m in val['messages'].values()]
        titles = ['Property Name', 'Value', 'Type', 'Exists', 'Result']
        widths = ['15', '30', '30', '10', '15']
        tableHeader = tableBlock(rows, titles, widths, ffunc=applySuccessColor)

        #    lets wrap table and errors and warns into one single column table
        tableHeader = tag.tr(tag.td((tableHeader)))

        infos_a = [str(val.get(x)) for x in ['uri'] if val.get(x) not in ['',None]]
        infos_a.append(rtime)

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


def htmlLogScraper(htmlReport, output_name=None):
    outputLogName = os.path.split(htmlReport)[-1] if not output_name else output_name
    output = open('./{}.csv'.format(outputLogName),'w',newline='')
    csv_output = csv.writer(output)
    csv_output.writerow(['URI','Status','Response Time','Context','File Origin','Resource Type','Property Name','Value','Expected','Actual','Result'])
    htmlLog = open(htmlReport,'r')
    soup = BeautifulSoup(htmlLog, 'html.parser')
    glanceDetails = {}
    table = soup.find_all('table', {'class':'titletable'})
    for tbl in table:
        tr = tbl.find('tr')
        URIresp = tr.find('td',{'class':'title'}) # URI, response time, show results button
        URI = URIresp.text.partition('(')[0]
        responseTime = URIresp.text.partition('response time')[2].split(')')[0].strip(':s')
        StatusGET = tr.find('td',{'class':'pass'}) or tr.find('td',{'class':'fail'})
        if 'Success' in StatusGET.text:
            Status = '200'
        else:
            Status = '400'

        context,FileOrigin,ResourceType = ' ',' ',' '
        if 'Context:' in tr.find_all('td')[1].text:
            context = tr.find_all('td')[1].text.split('Context:')[1].split('File')[0]
        if 'File Origin'in tr.find_all('td')[1].text:
            FileOrigin = tr.find_all('td')[1].text.split('File Origin:')[1].split('Resource')[0]
        if 'Resource Type'in tr.find_all('td')[1].text:
            ResourceType = tr.find_all('td')[1].text.split('Resource Type:')[1]
        resNumHtml = tr.find('div', {'class':'button warn'})
        resNum = resNumHtml.attrs['onclick'].split(";")
        resNum = resNum[0].split("'")[1] if len(resNum) < 3 else resNum[1].split("'")[1]
        results = [ URI, Status, responseTime, context, FileOrigin, ResourceType ]
        glanceDetails[resNum] = results # mapping of results to their respective tables

    properties = soup.findAll('td',{'class':'results'})
    data = []
    for table in properties:
        tableID = table.attrs.get('id')
        if len(table.find_all('table')) == 0 or tableID in ['resMetadata', None]:
            continue
        tableBody = table.find_all('table')[-1]
        tableRows = tableBody.find_all('tr')[1:] #get rows from property tables excluding header
        for tr in tableRows:
            td = tr.find_all('td')
            row = [i.text for i in td]
            if tableID in glanceDetails:
                data.append(glanceDetails[tableID] + row)
    csv_output.writerows(data)
    output.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get an excel sheet of details shown in the HTML reports for the Redfish Service Validator')
    parser.add_argument('htmllog' ,type=str, help = 'Path of the HTML log to be converted to csv format' )
    parser.add_argument('--dest' ,type=str, help = 'Name of output' )
    args = parser.parse_args()

    htmlLogScraper(args.htmllog, args.dest) 
