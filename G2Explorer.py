#! /usr/bin/env python3
import argparse
import cmd
import csv
import glob
import json
import os
import re
import sys
import textwrap
import logging
import traceback
from collections import OrderedDict
import configparser
import subprocess
import readline
import atexit
from io import StringIO

# try: 
#     from rich.table import Table
#     from rich.console import Console
#     has_rich = True
# except: has_rich = False
 
try: 
    from prettytable import PrettyTable 
    from prettytable import ALL as PRETTY_TABLE_ALL
    try: #  supports both ptable and prettytable builds of prettytable (only prettytable has these styles)
        from prettytable import SINGLE_BORDER, DOUBLE_BORDER, MARKDOWN, ORGMODE
        pretty_table_style_available = True
    except:
        pretty_table_style_available = False
except: 
    print('\nPlease install python pretty table (pip3 install prettytable)\n')
    sys.exit(1)

# Import from Senzing
try:
    import G2Paths
    from G2Database import G2Database
    from senzing import G2ConfigMgr, G2Diagnostic, G2Engine, G2EngineFlags, G2Exception, G2IniParams, G2Product
except:

    # Fall back to pre-Senzing-Python-SDK style of imports.
    try:
        import G2Paths
        from G2Product import G2Product
        from G2Database import G2Database
        from G2Diagnostic import G2Diagnostic
        from G2Engine import G2Engine
        from G2IniParams import G2IniParams
        from G2ConfigMgr import G2ConfigMgr
        from G2Exception import G2Exception
    except:
        print('\nPlease export PYTHONPATH=<path to senzing python directory>\n')
        sys.exit(1)

# ==============================
class colors: 
    code = {}
    #--styles
    code['reset'] = '\033[0m'
    code['bold'] ='\033[01m'
    code['dim'] = '\033[02m'
    code['italics'] = '\033[03m'
    code['underline'] = '\033[04m'
    code['blink'] = '\033[05m'
    code['reverse'] = '\033[07m'
    code['strikethrough'] = '\033[09m'
    code['invisible'] = '\033[08m'
    #--foregrounds
    code['fg.black'] = '\033[30m'
    code['fg.white'] = '\033[97m'
    code['fg.blue'] = '\033[34m'
    code['fg.magenta'] = '\033[35m'
    code['fg.cyan'] = '\033[36m'
    code['fg.yellow'] = '\033[33m'
    code['fg.green'] = '\033[32m'
    code['fg.red'] = '\033[31m'
    code['fg.lightblack'] = '\033[90m'
    code['fg.lightwhite'] = '\033[37m'
    code['fg.lightblue'] = '\033[94m'
    code['fg.lightmagenta'] = '\033[95m'
    code['fg.lightcyan'] = '\033[96m'
    code['fg.lightyellow'] = '\033[93m'
    code['fg.lightgreen'] = '\033[92m'
    code['fg.lightred'] = '\033[91m'
    #--backgrounds
    code['bg.black'] = '\033[40m'
    code['bg.white'] = '\033[107m'
    code['bg.blue'] = '\033[44m'
    code['bg.magenta'] = '\033[45m'
    code['bg.cyan'] = '\033[46m'
    code['bg.yellow'] = '\033[43m'
    code['bg.green'] = '\033[42m'
    code['bg.red'] = '\033[41m'
    code['bg.lightblack'] = '\033[100m'
    code['bg.lightwhite'] = '\033[47m'
    code['bg.lightblue'] = '\033[104m'
    code['bg.lightmagenta'] = '\033[105m'
    code['bg.lightcyan'] = '\033[106m'
    code['bg.lightyellow'] = '\033[103m'
    code['bg.lightgreen'] = '\033[102m'
    code['bg.lightred'] = '\033[101m'

    wheel = {}
    for color in code.keys():
        if color.startswith('fg.') and color not in ('fg.black','fg.white', 'fg.lightwhite','fg.lightblack'):
            wheel[len(wheel)] = color
    #for color1 in ['bg.black', 'bg.white']:
    #    for color2 in code.keys():
    #        if color2.startswith('fg.') and color2[2:] != color1[2:]:
    #            wheel[len(wheel)] = ','.join([color1, color2])

def colorize(string, colorList = None):
    if colorList: 
        prefix = ''.join([colors.code[i.strip().lower()] for i in colorList.split(',')])
        suffix = colors.code['reset']
        return f'{prefix}{string}{suffix}'
    return string

# ==============================
class ColoredTable(PrettyTable):

    def __init__(self, field_names=None, **kwargs):
        new_options = ['title_color', 'header_color', 'title_justify']

        super(ColoredTable, self).__init__(field_names, **kwargs)

        self.title_color = kwargs['title_color'] or None
        self.header_color = kwargs['header_color'] or None
        self.title_justify = kwargs['title_justify'] or 'c'

        self._options.extend(new_options)

        # hrule styles
        self.FRAME = 0
        self.ALL = 1

    def _stringify_title(self, title, options):

        lines = []
        lpad, rpad = self._get_padding_widths(options)
        if options["border"]:
            if options["vrules"] == self.ALL:
                options["vrules"] = self.FRAME
                lines.append(self._stringify_hrule(options))
                options["vrules"] = self.ALL
            elif options["vrules"] == self.FRAME:
                lines.append(self._stringify_hrule(options))
        bits = []
        endpoint = options["vertical_char"] if options["vrules"] in (self.ALL, self.FRAME) else " "
        bits.append(endpoint)
        title = " " * lpad + title + " " * rpad

        if options['title_color']:
            bits.append(colorize(self._justify(title, len(self._hrule) - 2, options['title_justify']), options['title_color']))
        else:
            bits.append(self._justify(title, len(self._hrule) - 2, options['title_justify']))

        bits.append(endpoint)
        lines.append("".join(bits))
        return "\n".join(lines)

    def _stringify_header(self, options):

        bits = []
        lpad, rpad = self._get_padding_widths(options)
        if options["border"]:
            if options["hrules"] in (self.ALL, self.FRAME):
                bits.append(self._hrule)
                bits.append("\n")
            if options["vrules"] in (self.ALL, self.FRAME):
                bits.append(options["vertical_char"])
            else:
                bits.append(" ")
        # For tables with no data or field names
        if not self._field_names:
            if options["vrules"] in (self.ALL, self.FRAME):
                bits.append(options["vertical_char"])
            else:
                bits.append(" ")
        for field, width, in zip(self._field_names, self._widths):
            if options["fields"] and field not in options["fields"]:
                continue
            if self._header_style == "cap":
                fieldname = field.capitalize()
            elif self._header_style == "title":
                fieldname = field.title()
            elif self._header_style == "upper":
                fieldname = field.upper()
            elif self._header_style == "lower":
                fieldname = field.lower()
            else:
                fieldname = field

            #if options['header_color']:
            #    fieldname = colorify(fieldname, options['header_color'])
            if options['header_color']:
                bits.append(colorize(" " * lpad
                            + self._justify(fieldname, width, self._align[field])
                            + " " * rpad, options['header_color']))
            else:
                bits.append(" " * lpad
                            + self._justify(fieldname, width, self._align[field])
                            + " " * rpad)
            if options["border"]:
                if options["vrules"] == self.ALL:
                    bits.append(options["vertical_char"])
                else:
                    bits.append(" ")
        # If vrules is FRAME, then we just appended a space at the end
        # of the last field, when we really want a vertical character
        if options["border"] and options["vrules"] == self.FRAME:
            bits.pop()
            bits.append(options["vertical_char"])
        if options["border"] and options["hrules"] is not None:
            bits.append("\n")
            bits.append(self._hrule)
        return "".join(bits)

# ==============================
class Node(object):
    def __init__(self, node_id):
        self.node_id = node_id
        self.node_desc = node_id
        self.node_text = None
        self.children = []

    def add_child(self, obj):
        self.children.append(obj)

    def render_tree(self):
        tree = ''
        tree += (self.node_desc + '\n')
        parents = [{'node': self, 'next_child': 0, 'prior_nodes': [self]}]
        while parents:
            if parents[-1]['next_child'] == len(parents[-1]['node'].children):
                parents.pop()
                continue

            next_node = parents[-1]['node'].children[parents[-1]['next_child']]
            parents[-1]['next_child'] += 1

            prefix = ''
            for i in range(len(parents)):
                if i < len(parents) - 1: #--prior level
                    prefix += ('    ' if parents[i]['next_child'] == len(parents[i]['node'].children) else '¦   ')
                else:
                    prefix += ('+-- ' if parents[i]['next_child'] == len(parents[i]['node'].children) else '+-- ')

            tree += (prefix + next_node.node_desc + '\n')
            if next_node.node_text:
                if prefix[-4:] == '+-- ':
                    prefix = prefix[0:-4] + '¦   '
                elif prefix[-4:] == '+-- ':
                    prefix = prefix[0:-4] + '    '

                for line in next_node.node_text.split('\n'):
                    tree += (prefix + line + '\n')

            if next_node not in parents[-1]['prior_nodes'] and next_node.children:
                #--gather all prior level nodes so don't render twice
                prior_nodes = []
                for parent in parents:
                    prior_nodes += parent['node'].children

                parents.append({'node': next_node, 'next_child': 0, 'prior_nodes': prior_nodes})
        return tree

# ==============================
class G2CmdShell(cmd.Cmd):

    def __init__(self):
        cmd.Cmd.__init__(self)
        readline.set_completer_delims(' ')
        self.usePrettyTable = True

        self.intro = '\nType help or ? to list commands.\n'
        self.prompt = prompt

        #--store config dicts for fast lookup
        self.cfgData = cfgData
        self.dsrcLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_DSRC']:
            self.dsrcLookup[cfgRecord['DSRC_ID']] = cfgRecord 
        self.dsrcCodeLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_DSRC']:
            self.dsrcCodeLookup[cfgRecord['DSRC_CODE']] = cfgRecord 
        self.etypeLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_ETYPE']:
            self.etypeLookup[cfgRecord['ETYPE_ID']] = cfgRecord 
        self.erruleLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_ERRULE']:
            self.erruleLookup[cfgRecord['ERRULE_ID']] = cfgRecord 
        self.erruleCodeLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_ERRULE']:
            self.erruleCodeLookup[cfgRecord['ERRULE_CODE']] = cfgRecord 
        self.ftypeLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_FTYPE']:
            self.ftypeLookup[cfgRecord['FTYPE_ID']] = cfgRecord 
        self.ftypeCodeLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_FTYPE']:
            self.ftypeCodeLookup[cfgRecord['FTYPE_CODE']] = cfgRecord 

        self.ftypeAttrLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_ATTR']:
            if cfgRecord['FTYPE_CODE'] not in self.ftypeAttrLookup:
                self.ftypeAttrLookup[cfgRecord['FTYPE_CODE']] = {}
            self.ftypeAttrLookup[cfgRecord['FTYPE_CODE']][cfgRecord['FELEM_CODE']] = cfgRecord 

        self.cfuncLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_CFUNC']:
            self.cfuncLookup[cfgRecord['CFUNC_ID']] = cfgRecord 

        self.cfrtnLookup = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_CFRTN']:
            self.cfrtnLookup[cfgRecord['CFUNC_ID']] = cfgRecord 

        self.scoredFtypeCodes = {}
        for cfgRecord in self.cfgData['G2_CONFIG']['CFG_CFCALL']:
            cfgRecord['FTYPE_CODE'] = self.ftypeLookup[cfgRecord['FTYPE_ID']]['FTYPE_CODE']
            cfgRecord['CFUNC_CODE'] = self.cfuncLookup[cfgRecord['CFUNC_ID']]['CFUNC_CODE']
            self.scoredFtypeCodes[cfgRecord['FTYPE_CODE']] = cfgRecord 

        self.ambiguousFtypeID = self.ftypeCodeLookup['AMBIGUOUS_ENTITY']['FTYPE_ID']

        #--set feature display sequence
        self.featureSequence = {}
        self.featureSequence[self.ambiguousFtypeID] = 1 #--ambiguous is first
        featureSequence = 2 
        #--scored features second        
        for cfgRecord in sorted(self.cfgData['G2_CONFIG']['CFG_CFCALL'], key=lambda k: k['FTYPE_ID']):
            if cfgRecord['FTYPE_ID'] not in self.featureSequence:
                self.featureSequence[cfgRecord['FTYPE_ID']] = featureSequence
                featureSequence += 1
        #--then the rest
        for cfgRecord in sorted(self.cfgData['G2_CONFIG']['CFG_FTYPE'], key=lambda k: k['FTYPE_ID']):
            if cfgRecord['FTYPE_ID'] not in self.featureSequence:
                self.featureSequence[cfgRecord['FTYPE_ID']] = featureSequence
                featureSequence += 1

        #--misc
        self.dsrc_record_sep = '~|~'
        self.__hidden_methods = ('do_shell')
        self.doDebug = False
        self.searchMatchLevels = {1: 'Match', 2: 'Possible Match', 3: 'Possibly Related', 4: 'Name Only'}
        self.relatedMatchLevels = {1: 'Ambiguous Match', 2: 'Possible Match', 3: 'Possibly Related', 4: 'Name Only', 11: 'Disclosed Relation'}
        self.validMatchLevelParameters = {}
        self.validMatchLevelParameters['0'] = 'SINGLE_SAMPLE'
        self.validMatchLevelParameters['1'] = 'DUPLICATE_SAMPLE'
        self.validMatchLevelParameters['2'] = 'AMBIGUOUS_MATCH_SAMPLE'
        self.validMatchLevelParameters['3'] = 'POSSIBLE_MATCH_SAMPLE'
        self.validMatchLevelParameters['4'] = 'POSSIBLY_RELATED_SAMPLE'
        self.validMatchLevelParameters['SINGLE'] = 'SINGLE_SAMPLE'
        self.validMatchLevelParameters['DUPLICATE'] = 'DUPLICATE_SAMPLE'
        self.validMatchLevelParameters['MATCH'] = 'DUPLICATE_SAMPLE'
        self.validMatchLevelParameters['AMBIGUOUS'] = 'AMBIGUOUS_MATCH_SAMPLE'
        self.validMatchLevelParameters['POSSIBLE'] = 'POSSIBLE_MATCH_SAMPLE'
        self.validMatchLevelParameters['POSSIBLY'] = 'POSSIBLY_RELATED_SAMPLE'
        self.validMatchLevelParameters['RELATED'] = 'POSSIBLY_RELATED_SAMPLE'
        self.validMatchLevelParameters['S'] = 'SINGLE_SAMPLE'
        self.validMatchLevelParameters['D'] = 'DUPLICATE_SAMPLE'
        self.validMatchLevelParameters['M'] = 'DUPLICATE_SAMPLE'
        self.validMatchLevelParameters['A'] = 'AMBIGUOUS_MATCH_SAMPLE'
        self.validMatchLevelParameters['P'] = 'POSSIBLE_MATCH_SAMPLE'
        self.validMatchLevelParameters['R'] = 'POSSIBLY_RELATED_SAMPLE'

        #--get settings
        settingsFileName = '.' + os.path.basename(sys.argv[0].lower().replace('.py','')) + '_settings'

        self.settingsFileName = os.path.join(os.path.expanduser("~"), settingsFileName)
        try: self.current_settings = json.load(open(self.settingsFileName))
        except: self.current_settings = {}

        #--default last snapshot/audit file from parameters
        if args.snapshot_file_name:
            self.current_settings['snapshotFile'] = args.snapshot_file_name
        if args.audit_file_name:
            self.current_settings['auditFile'] = args.audit_file_name

        #--load prior snapshot file
        if 'snapshotFile' in self.current_settings and os.path.exists(self.current_settings['snapshotFile']):
            self.do_load(self.current_settings['snapshotFile'])
        else:
            self.snapshotFile = None
            self.snapshotData = {}

        #--load prior audit file
        if 'auditFile' in self.current_settings and os.path.exists(self.current_settings['auditFile']):
            self.do_load(self.current_settings['auditFile'])
        else:
            self.auditFile = None
            self.auditData = {}

        #--default settings for data and cross sources summary reports
        self.configurable_settings_list = [
            {'setting': 'color_scheme', 'values': ['light', 'dark'], 'description': 'light works better on dark backgrounds and vice-versa'}, 
            {'setting': 'statistic_level', 'values': ['record', 'entity'], 'description': 'sets the statistical point of view of the data and crossSourceSummary reports'}, 
            {'setting': 'data_source_suppression', 'values': ['off', 'on'], 'description': 'restricts the data and crossSourceSummary reports to only applicable data sources'},
            {'setting': 'show_relations_on_get', 'values': ['off', 'on'], 'description': 'always display relationships if any with each get of an entity ... or not!'}
        ]
        for setting_data in self.configurable_settings_list:
            self.current_settings[setting_data['setting']] = self.current_settings.get(setting_data['setting'], setting_data['values'][0])

        #--set the color scheme
        self.colors = {}
        self.do_set(f"color_scheme {self.current_settings['color_scheme']}")

        self.lastSearchResult = []
        self.currentReviewList = None

        #--history
        self.readlineAvail = True if 'readline' in sys.modules else False
        self.histDisable = hist_disable
        self.histCheck()

    #Hide functions from available list of Commands. Seperate help sections for some
    def get_names(self):
        return [n for n in dir(self.__class__) if n not in self.__hidden_methods]

    #Override function from cmd module to make command completion case insensitive
    def completenames(self, text, *ignored):
        dotext = 'do_'+text
        return  [a[3:] for a in self.get_names() if a.lower().startswith(dotext.lower())]

    # -----------------------------
    def emptyline(self):
        return

    # -----------------------------
    def do_quit(self, arg):
        return True

    # -----------------------------
    def do_exit(self, arg):
        self.do_quit(self)
        return True

    # -----------------------------
    def cmdloop(self):
        while True:
            try: 
                cmd.Cmd.cmdloop(self)
                break
            except KeyboardInterrupt:
                ans = input('\n\nAre you sure you want to exit?  ')
                if ans in ['y','Y', 'yes', 'YES']:
                    break
            except TypeError as ex:
                printWithNewLines("ERROR: " + str(ex))
                type_, value_, traceback_ = sys.exc_info()
                for item in traceback.format_tb(traceback_):
                    printWithNewLines(item)

    def postloop(self):
        try:
            with open(self.settingsFileName, 'w') as f:
                json.dump(self.current_settings, f)
        except: pass

    def help_KnowledgeCenter(self):
        printWithNewLines('Senzing Knowledge Center: https://senzing.zendesk.com/hc/en-us', 'B')

    def help_Support(self):
        printWithNewLines('Senzing Support Request: https://senzing.zendesk.com/hc/en-us/requests/new', 'B')


    def help_Arguments(self):
        print(
              '\nWhere you see <value> in the help output replace <value> with your value.\n' \
              '\nFor example the help for addAttribute is: \n' \
              '\taddAttribute {"attribute": "<attribute_name>"}\n' \
              '\nReplace <attribute_name> to be the name of your new attribute\n' \
              '\taddAttribute {"attribute": "myNewAttribute"}\n' \
              )

    def help_Shell(self):
        printWithNewLines('Run OS shell commands: ! <command>', 'B')

    def help_History(self):
        printWithNewLines(textwrap.dedent(f'''\
            - Use shell like history, requires Python readline module.

            - Tries to create a history file in the users home directory for use across instances of G2ConfigTool. 

            - If a history file can't be created in the users home, /tmp is tried for temporary session history. 

            - Ctrl-r can be used to search history when history is available

            - Commands to manage history

                - histClear = Clears the current working session history and the history file. This deletes all history, be careful!
                - histDedupe = The history can accumulate duplicate entries over time, use this to remove them
                - histShow = Display all history

            - History Status: 
                - Readline available: {self.readlineAvail}
                - History available: {self.histAvail}
                - History file: {self.histFileName}
                - History file error: {self.histFileError}
            '''), 'S')


    def histCheck(self):
        '''  '''
    
        self.histFileName = None
        self.histFileError = None
        self.histAvail = False
    
        if not self.histDisable:
    
            if readline:
                tmpHist = '.' + os.path.basename(sys.argv[0].lower().replace('.py','_history'))
                self.histFileName = os.path.join(os.path.expanduser('~'), tmpHist)
    
                #Try and open history in users home first for longevity 
                try:
                    open(self.histFileName, 'a').close()
                except IOError as e:
                    self.histFileError = f'{e} - Couldn\'t use home, trying /tmp/...'
    
                #Can't use users home, try using /tmp/ for history useful at least in the session
                if self.histFileError:
    
                    self.histFileName = f'/tmp/{tmpHist}'
                    try:
                        open(self.histFileName, 'a').close()
                    except IOError as e:
                        self.histFileError = f'{e} - User home dir and /tmp/ failed!'
                        return
    
                hist_size = 2000
                readline.read_history_file(self.histFileName)
                readline.set_history_length(hist_size)
                atexit.register(readline.set_history_length, hist_size)
                atexit.register(readline.write_history_file, self.histFileName)
                
                self.histFileName = self.histFileName
                self.histFileError = None
                self.histAvail = True   


    def do_histDedupe(self, arg):

        if self.histAvail:
            if input('\nThis will de-duplicate both this session history and the history file, are you sure? (y/n)  ') in ['y','Y', 'yes', 'YES']:
    
                with open(self.histFileName) as hf:
                    linesIn = (line.rstrip() for line in hf)
                    uniqLines = OrderedDict.fromkeys( line for line in linesIn if line )
    
                    readline.clear_history()
                    for ul in uniqLines:
                        readline.add_history(ul)
    
                printWithNewLines('Session history and history file both deduplicated.', 'B')
            else:
                print()
        else:
            printWithNewLines('History isn\'t available in this session.', 'B')


    def do_histClear(self, arg):

        if self.histAvail:
            if input('\nThis will clear both this session history and the history file, are you sure? (y/n)  ') in ['y','Y', 'yes', 'YES']:
                readline.clear_history()
                readline.write_history_file(self.histFileName)
                printWithNewLines('Session history and history file both cleared.', 'B')
            else:
                print()
        else:
            printWithNewLines('History isn\'t available in this session.', 'B')


    def do_histShow(self, arg):

        if self.histAvail:
            print()
            for i in range(readline.get_current_history_length()):
                printWithNewLines(readline.get_history_item(i + 1))
            print()
        else:
            printWithNewLines('History isn\'t available in this session.', 'B')

    # -----------------------------
    def do_shell(self,line):
        '\nRun OS shell commands: !<command>\n'
        output = os.popen(line).read()
        print(f"\n{output}\n")

    # -----------------------------
    def help_set (self):
        print(textwrap.dedent(f'''\

            {colorize('syntax:', self.colors['highlight1'])} 
                set <setting> <value> 

            {colorize('settings:', self.colors['highlight1'])} '''))
        print(colorize(f"    {'setting':<25} {'[possible values]':<20} {'current':<11} {'description'}", 'bold'))
        for setting_data in self.configurable_settings_list:
            current_value = colorize(self.current_settings[setting_data['setting']], self.colors['highlight2'])
            print(f"    {setting_data['setting']:<25} {'[' + ', '.join(setting_data['values']) + ']':<20} {current_value:<20} {setting_data['description']}")
        print()

    # -----------------------------
    def do_set(self,arg):
        if not arg:
            self.help_set()
            return

        settings_dict = {}
        for setting_data in self.configurable_settings_list:
            settings_dict[setting_data['setting']] = setting_data['values']

        arg_list = arg.split()
        if len(arg_list) != 2 or (arg_list[0] not in settings_dict) or (arg_list[1] not in settings_dict[arg_list[0]]):
            print('['+arg_list[0]+']', arg_list[0] in [item['setting'] for item in self.configurable_settings_list])
            print(colorize('\ninvalid syntax or settings\n', 'fg.red'))
            self.help_set()
            return

        self.current_settings[arg_list[0]] = arg_list[1]
        if arg_list[0] == 'color_scheme':
            self.set_color_scheme(arg_list[1])

    # -----------------------------
    def set_color_scheme(self,arg):
        self.colors['none'] = None
        if arg.upper() == 'LIGHT':
            self.current_settings['colorScheme'] = 'light'
            self.colors['entityTitle'] = 'fg.lightmagenta'
            self.colors['entityColumns'] = 'bg.lightblack,fg.white'
            self.colors['tableTitle'] = 'fg.lightblue'
            self.colors['rowtitle'] = 'fg.lightblue'
            self.colors['columnHeader'] = 'fg.lightblue,italics'
            self.colors['entityid'] = 'fg.lightmagenta,bold'
            self.colors['datasource'] = 'fg.lightyellow,bold'
            self.colors['good'] = 'fg.lightgreen'
            self.colors['bad'] = 'fg.lightred'
            self.colors['caution'] = 'fg.lightyellow'
            self.colors['highlight1'] = 'fg.lightcyan'
            self.colors['highlight2'] = 'fg.lightmagenta'

        #--best for light backgrounds
        elif arg.upper() == 'DARK':
            self.current_settings['colorScheme'] = 'dark'
            self.colors['entityTitle'] = 'fg.magenta'
            self.colors['entityColumns'] = 'bg.lightblack,fg.white'
            self.colors['tableTitle'] = 'fg.blue'
            self.colors['rowtitle'] = 'fg.blue'
            self.colors['columnHeader'] = 'fg.blue,italics'
            self.colors['entityid'] = 'fg.magenta,bold'
            self.colors['datasource'] = 'fg.yellow,bold'
            self.colors['good'] = 'fg.green'
            self.colors['bad'] = 'fg.red'
            self.colors['caution'] = 'fg.yellow'
            self.colors['highlight1'] = 'fg.cyan'
            self.colors['highlight2'] = 'fg.magenta'

    # -----------------------------
    def do_versions (self,arg):
        '\nDisplays current and snapshot version information.\n'
        print()
        print('current api version is:', apiVersion['BUILD_VERSION'])
        if self.snapshotFile:
            if self.snapshotData and 'API_VERSION' in self.snapshotData: 
                print('snapshot api version was:', self.snapshotData['API_VERSION'])
            if self.snapshotData and 'RUN_DATE' in self.snapshotData: 
                print('snapshot run date and time was:', self.snapshotData['RUN_DATE'])
        print()

    # -----------------------------
    def do_load (self,arg):
        '\nLoads statistical json files computed by G2Snapshot.py and G2Audit.py.' \
        '\n\nSyntax:' \
        '\n\tload <snapshotFile.json>' \
        '\n\tload <auditFile.json>\n'
        if not argCheck('do_load', arg, self.do_load.__doc__):
            return

        statpackFileName = arg
        if not os.path.exists(statpackFileName):
            print('\nfile not found!\n')
            return

        try: jsonData = json.load(open(statpackFileName), encoding="utf-8")
        except ValueError as err:
            print(f"\nError in {statpackFileName} ...\n\t{err}\n")
            return

        if 'SOURCE' in jsonData and jsonData['SOURCE'] in ('G2Snapshot'): #--'pocSnapshot', 
            self.current_settings['snapshotFile'] = statpackFileName
            self.snapshotFile = statpackFileName
            self.snapshotData = jsonData
            print(f"\nsucessfully loaded {statpackFileName}\n")
        elif 'SOURCE' in jsonData and jsonData['SOURCE'] in ('G2Audit'): #--'pocAudit', 
            self.current_settings['auditFile'] = statpackFileName
            self.auditFile = statpackFileName
            self.auditData = jsonData
            print(f"\nsucessfully loaded {statpackFileName}\n")
        else:
            print('\ninvalid G2Explorer statistics file\n')

    # -----------------------------
    def complete_load(self, text, line, begidx, endidx):
        before_arg = line.rfind(" ", 0, begidx)
        if before_arg == -1:
            return # arg not found

        fixed = line[before_arg+1:begidx]  # fixed portion of the arg
        arg = line[before_arg+1:endidx]
        pattern = arg + '*'

        completions = []
        for path in glob.glob(pattern):
            path = _append_slash_if_dir(path)
            completions.append(path.replace(fixed, "", 1))
        return completions

    # -----------------------------
    def xx_perfStats (self,arg):
        '\nDisplays the performance stats of the snapshot'

        if not self.snapshotData or 'PERF' not in self.snapshotData:
            printWithNewLines('Performance stats not available on the loaded snapshot file', 'B')
            return

        print('\nPerformance statistics ...')
        for stat in self.snapshotData['PERF']:
            print(('  ' + stat + ' ' + '.' * 30)[0:30] + ' ' + (str(self.snapshotData['PERF'][stat])))

        print()

    # -----------------------------
    def do_quickLook (self,arg):
        '\nDisplays current data source stats without a snapshot'

        g2_diagnostic_module = G2Diagnostic()
        if apiVersion['VERSION'][0:1] == '2':
            g2_diagnostic_module.initV2('pyG2Diagnostic', iniParams, False)
        else: #--eventually deprecate the above
            g2_diagnostic_module.init('pyG2Diagnostic', iniParams, False)

        try: 
            response = bytearray() 
            g2_diagnostic_module.getDataSourceCounts(response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print(err)
        jsonResponse = json.loads(response)

        tblTitle = 'Data source counts'
        tblColumns = []
        tblColumns.append({'name': 'id', 'width': 5, 'align': 'center'})
        tblColumns.append({'name': 'DataSource', 'width': 30, 'align': 'left'})
        tblColumns.append({'name': 'EntityType', 'width': 30, 'align': 'left'})
        tblColumns.append({'name': 'ActualRecordCount', 'width': 20, 'align': 'right'})
        tblColumns.append({'name': 'DistinctRecordCount', 'width': 20, 'align': 'right'})
        tblRows = []
        for row in jsonResponse:
            entityType = '' if row['ETYPE_CODE'] == 'GENERIC' or row['ETYPE_CODE'] == row['DSRC_CODE'] else ''
            tblRows.append([colorize(row['DSRC_ID'], self.colors['rowtitle']),
                            colorize(row['DSRC_CODE'], self.colors['datasource']),
                            colorize(entityType, self.colors['datasource']),
                            row['DSRC_RECORD_COUNT'],
                            row['OBS_ENT_COUNT']])
        self.renderTable(tblTitle, tblColumns, tblRows)

        g2_diagnostic_module.destroy()


    # -----------------------------
    def do_auditSummary (self,arg):
        '\nDisplays the stats and examples of an audit performed with G2Audit.py' \
        '\n\nSyntax:' \
        '\n\tauditSummary         (with no parameters displays the overall stats)' \
        '\n\tauditSummary merge   (shows a list of merge sub-categories)' \
        '\n\tauditSummary merge 1 (shows examples of merges in sub-category 1)' \
        '\n\tauditSummary split   (shows a list of split sub-categories)' \
        '\n\tauditSummary split 1 (shows examples of splits in sub-category 1)' \
        '\n\tauditSummary save to <filename.csv> (saves the entire audit report to a csv file)\n'

        if not self.auditData or 'AUDIT' not in self.auditData:
            printWithNewLines('Please load a json file created with G2Audit.py to use this command', 'B')
            return

        categoryColors = {}
        categoryColors['MERGE'] = self.colors['good']
        categoryColors['SPLIT'] = self.colors['bad']
        categoryColors['SPLIT+MERGE'] = 'fg.red,bg.green'
        categoryColors['unknown'] = 'bg.red,fg.white'

        #--display the summary if no arguments
        if not arg:
            
            auditCategories = []
            categoryOrder = {'MERGE': 0, 'SPLIT': 1, 'SPLIT+MERGE': 2}
            for category in sorted(self.auditData['AUDIT'].keys(), key=lambda x: categoryOrder[x] if x in categoryOrder else 9):
                categoryColor = categoryColors[category] if category in categoryColors else categoryColors['unknown']
                categoryData = [colorize(category, categoryColor), colorize(fmtStatistic(self.auditData['AUDIT'][category]['COUNT']), 'bold')]
                auditCategories.append(categoryData)
            while len(auditCategories) < 3:
                auditCategories.append(['', 0])


            tblTitle = 'Audit Summary from %s' % self.auditFile
            tblColumns = []
            tblColumns.append({'name': 'Statistic1', 'width': 25, 'align': 'left'})
            tblColumns.append({'name': 'Entities', 'width': 25, 'align': 'right'})
            tblColumns.append({'name': 'Clusters', 'width': 25, 'align': 'right'})
            tblColumns.append({'name': 'Pairs', 'width': 25, 'align': 'right'})
            tblColumns.append({'name': colorize('-', 'invisible'), 'width': 5, 'align': 'center'})
            tblColumns.append({'name': 'Statistic2', 'width': 25, 'align': 'left'})
            tblColumns.append({'name': 'Accuracy', 'width': 25, 'align': 'right'})
            tblRows = []

            row = []
            row.append(colorize('Prior Count', self.colors['highlight1']))
            row.append(fmtStatistic(self.auditData['ENTITY']['STANDARD_COUNT']) if 'ENTITY' in self.auditData else '0')
            row.append(fmtStatistic(self.auditData['CLUSTERS']['STANDARD_COUNT']))
            row.append(fmtStatistic(self.auditData['PAIRS']['STANDARD_COUNT']))
            row.append('')
            row.append(colorize('Prior Positives', self.colors['highlight1']))
            row.append(colorize(fmtStatistic(self.auditData['ACCURACY']['PRIOR_POSITIVE']), None))
            tblRows.append(row)

            row = []
            row.append(colorize('Newer Count', self.colors['highlight1']))
            row.append(fmtStatistic(self.auditData['ENTITY']['RESULT_COUNT']) if 'ENTITY' in self.auditData else '0')
            row.append(fmtStatistic(self.auditData['CLUSTERS']['RESULT_COUNT']))
            row.append(fmtStatistic(self.auditData['PAIRS']['RESULT_COUNT']))
            row.append('')
            row.append(colorize('New Positives', categoryColors['MERGE']))
            row.append(colorize(fmtStatistic(self.auditData['ACCURACY']['NEW_POSITIVE']), None))
            tblRows.append(row)

            row = []
            row.append(colorize('Common Count', self.colors['highlight1']))
            row.append(fmtStatistic(self.auditData['ENTITY']['COMMON_COUNT']) if 'ENTITY' in self.auditData else '0')
            row.append(fmtStatistic(self.auditData['CLUSTERS']['COMMON_COUNT']))
            row.append(fmtStatistic(self.auditData['PAIRS']['COMMON_COUNT']))
            row.append('')
            row.append(colorize('New Negatives', categoryColors['SPLIT']))
            row.append(colorize(fmtStatistic(self.auditData['ACCURACY']['NEW_NEGATIVE']), None))
            tblRows.append(row) 

            row = []
            row.append(auditCategories[0][0])
            row.append(auditCategories[0][1])
            row.append('') #(colorize(self.auditData['CLUSTERS']['INCREASE'], self.colors['good']) if self.auditData['CLUSTERS']['INCREASE'] else '')
            row.append('') #(colorize(self.auditData['PAIRS']['INCREASE'], self.colors['good']) if self.auditData['PAIRS']['INCREASE'] else '')
            row.append('')
            row.append(colorize('Precision', self.colors['highlight1']))
            row.append(colorize(self.auditData['ACCURACY']['PRECISION'], None))
            tblRows.append(row)

            row = []
            row.append(auditCategories[1][0])
            row.append(auditCategories[1][1])
            row.append('') #(colorize(self.auditData['CLUSTERS']['DECREASE'], self.colors['bad']) if self.auditData['CLUSTERS']['DECREASE'] else '')
            row.append('') #(colorize(self.auditData['PAIRS']['DECREASE'], self.colors['bad']) if self.auditData['PAIRS']['DECREASE'] else '')
            row.append('')
            row.append(colorize('Recall', self.colors['highlight1']))
            row.append(colorize(self.auditData['ACCURACY']['RECALL'], None))
            tblRows.append(row)

            row = []
            row.append(auditCategories[2][0])
            row.append(auditCategories[2][1])
            row.append('') #(colorize(self.auditData['CLUSTERS']['SIMILAR'], self.colors['highlight1']) if self.auditData['CLUSTERS']['SIMILAR'] else '')
            row.append('') #(colorize(self.auditData['PAIRS']['SIMILAR'], self.colors['highlight1']) if self.auditData['PAIRS']['SIMILAR'] else '')
            row.append('')
            row.append(colorize('F1 Score', self.colors['highlight1']))
            row.append(colorize(self.auditData['ACCURACY']['F1-SCORE'], None))
            tblRows.append(row)

            #--add any extra categories (which will occur if there were missing records)
            if len(auditCategories) > 3:
                i = 3
                while i < len(auditCategories):
                    row = []
                    row.append(auditCategories[i][0])
                    row.append(auditCategories[i][1])
                    row.append('')
                    row.append('')
                    row.append('')
                    row.append('')
                    row.append('')
                    tblRows.append(row)
                    i += 1

            self.renderTable(tblTitle, tblColumns, tblRows)

        #--build complete report and save to a file
        elif arg.upper().startswith('SAVE'):
            
            fileName = arg[7:].strip()
            fileHeaders = ['category', 'sub_category', 'audit_id']
            fileRows = []
            rowCnt = 0
            for category in self.auditData['AUDIT']:
                for subCategory in self.auditData['AUDIT'][category]['SUB_CATEGORY']:
                    for sampleRecords in self.auditData['AUDIT'][category]['SUB_CATEGORY'][subCategory]['SAMPLE']:
                        tableColumns, tableData = self.auditResult(sampleRecords, None) #--2nd parmater cuts out colorize for save to file
                        recordHeaders = []
                        for columnDict in tableColumns:
                            columnName = columnDict['name'].lower()
                            if columnName not in recordHeaders:
                                recordHeaders.append(columnName)
                            if columnName not in fileHeaders:
                                fileHeaders.append(columnName)
                        for recordData in tableData:
                            #print(tableHeaders)
                            #print(rowData)
                            rowData = dict(zip(recordHeaders, recordData))
                            rowData['category'] = category
                            rowData['sub_category'] = subCategory
                            rowData['audit_id'] = sampleRecords[0]['audit_id']
                            fileRows.append(rowData)
                            rowCnt += 1
                            if rowCnt % 1000 == 0:
                                print('%s records processed' % rowCnt)

            with open(fileName, 'w', encoding='utf-8') as f:
                w = csv.DictWriter(f, fileHeaders, dialect=csv.excel, quoting=csv.QUOTE_ALL)
                w.writeheader()
                for rowData in fileRows:
                    w.writerow(rowData)
            print('%s records written to %s' % (rowCnt, fileName))


        #--display next level report
        else:
            argList = arg.upper().split()
            if argList[0] not in self.auditData['AUDIT']:
                printWithNewLines('%s not found, please choose a valid split or merge category' % arg, 'B')
                return

            category = argList[0]
            categoryColor = categoryColors[category] if category in categoryColors else categoryColors['unknown']

            #--get top 10 sub categories
            i = 0
            subCategoryList = []
            for subCategory in sorted(self.auditData['AUDIT'][category]['SUB_CATEGORY'], key=lambda x: self.auditData['AUDIT'][category]['SUB_CATEGORY'][x]['COUNT'], reverse=True):

                i += 1
                if i <= 10:
                    subCategoryList.append({'INDEX': i, 'NAME': subCategory, 'LIST': [subCategory], 'COUNT': self.auditData['AUDIT'][category]['SUB_CATEGORY'][subCategory]['COUNT']})
                elif i == 11:
                    subCategoryList.append({'INDEX': i, 'NAME': 'OTHERS', 'LIST': [subCategory], 'COUNT': self.auditData['AUDIT'][category]['SUB_CATEGORY'][subCategory]['COUNT']})
                else:
                    subCategoryList[10]['LIST'].append(subCategory)
                    subCategoryList[10]['COUNT'] += self.auditData['AUDIT'][category]['SUB_CATEGORY'][subCategory]['COUNT']

            #--display sub-categories
            if len(argList) == 1:
                tblTitle = category + ' Categories'
                tblColumns = []
                tblColumns.append({'name': 'Index', 'width': 10, 'align': 'center'})
                tblColumns.append({'name': 'Category', 'width': 25, 'align': 'left'})
                tblColumns.append({'name': 'Sub-category', 'width': 75, 'align': 'left'})
                tblColumns.append({'name': 'Count', 'width': 25, 'align': 'right'})
                tblRows = []
                for subCategoryRow in subCategoryList:
                    tblRows.append([str(subCategoryRow['INDEX']), colorize(category, categoryColor), subCategoryRow['NAME'], fmtStatistic(subCategoryRow['COUNT'])])
                self.renderTable(tblTitle, tblColumns, tblRows)

                return

            #--find the detail records to display
            indexCategories = []
            if argList[1].isdigit():
                for subCategoryRow in subCategoryList:
                    if subCategoryRow['INDEX'] == int(argList[1]):
                        indexCategories = subCategoryRow['LIST']
                        break

            if not indexCategories:
                printWithNewLines('Invalid subcategory for %s' % argList[0].lower(), 'B')
                return

            #--gather sample records
            sampleRecords = []
            for subCategory in self.auditData['AUDIT'][category]['SUB_CATEGORY']:
                if subCategory in indexCategories:
                    sampleRecords += self.auditData['AUDIT'][category]['SUB_CATEGORY'][subCategory]['SAMPLE']

            #--display sample records
            currentSample = 0
            while True:

                self.auditResult(sampleRecords[currentSample], categoryColors)
                exportRecords = list(set([x['newer_id'] for x in sampleRecords[currentSample]]))

                while True:
                    reply = input('Select (P)revious, (N)ext, (S)croll, (W)hy, (E)xport, (Q)uit ... ')
                    if reply:
                        removeFromHistory()
                    else:
                        break

                    if reply.upper().startswith('R'): #--reload
                        break
                    elif reply.upper().startswith('P'): #--previous
                        if currentSample == 0:
                            printWithNewLines('no prior records!', 'B')
                        else:
                            currentSample = currentSample - 1
                            break
                    elif reply.upper().startswith('N'): #--next
                        if currentSample == len(sampleRecords) - 1:
                            printWithNewLines('no more records!', 'B')
                        else:
                            currentSample += 1
                            break
                    elif reply.upper().startswith('Q'): #--quit
                        break

                    #--special actions 
                    elif reply.upper().startswith('S'): #--scrolling view
                        self.do_scroll('')
                    elif reply.upper().startswith('W2'): #--why view
                        self.do_why(','.join(exportRecords) + ' old')
                    elif reply.upper().startswith('W'): #--why view
                        self.do_why(','.join(exportRecords))
                    elif reply.upper().startswith('E'): #--export
                        fileName = None
                        if 'TO' in reply.upper():
                            fileName = reply[reply.upper().find('TO') + 2:].strip()
                        else:                            
                            fileName = 'auditSample-%s.json' % sampleRecords[currentSample][0]['audit_id']
                            #--fileName = os.path.join(os.path.expanduser("~"), fileName)
                        self.do_export(','.join(exportRecords) + 'to ' + fileName)

                if reply.upper().startswith('Q'):
                    break

    # -----------------------------
    def complete_auditSummary(self, text, line, begidx, endidx):
        before_arg = line.rfind(" ", 0, begidx)
        #if before_arg == -1:
        #    return # arg not found

        fixed = line[before_arg+1:begidx]  # fixed portion of the arg
        arg = line[before_arg+1:endidx]

        spaces = line.count(' ')
        if spaces <= 1:
            possibles = []
            if self.auditData:
                for category in self.auditData['AUDIT']:
                    possibles.append(category)
        else:
            possibles = []

        return [i for i in possibles if i.lower().startswith(arg.lower())]

    # -----------------------------
    def auditResult (self, arg, categoryColors = None):

        auditRecords = arg
        exportRecords = []

        tblTitle = 'Audit Result ID %s %s' % (auditRecords[0]['audit_id'], auditRecords[0]['audit_category'])
        tblColumns = []
        tblColumns.append({'name': 'DataSource', 'width': 30, 'align': 'left'})
        tblColumns.append({'name': 'Record ID', 'width': 30, 'align': 'left'})
        tblColumns.append({'name': 'Prior ID', 'width': 20, 'align': 'left'})
        tblColumns.append({'name': 'Prior Score', 'width': 75, 'align': 'left'})
        tblColumns.append({'name': 'Newer ID', 'width': 20, 'align': 'left'})
        tblColumns.append({'name': 'Newer Score', 'width': 75, 'align': 'left'})
        tblColumns.append({'name': 'Audit result', 'width': 10, 'align': 'left'})

        entityList = list(set([x['newer_id'] for x in auditRecords]))

        getFlagList = []
        if apiVersion['VERSION'][0:1] > '1':
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
            getFlagList.append('G2_ENTITY_INCLUDE_ENTITY_NAME')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_DATA')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_MATCHING_INFO')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_FEATURE_IDS')
        else:
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
        getFlagBits = self.computeApiFlags(getFlagList)

        #--gather all the record data
        ftypesUsed = []
        recordList = []
        entityList = set([x['newer_id'] for x in auditRecords])
        for entityId in entityList:
            if entityId == 'unknown':  #--bypass missing
                continue
            try: 
                response = bytearray()
                retcode = g2Engine.getEntityByEntityIDV2(int(entityId), getFlagBits, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print('\n' + str(err) + '\n')
                return -1 if calledDirect else 0

            if len(response) == 0:
                return None
            jsonData = json.loads(response)

            if debugOutput:
                apiCall = f'getEntityByEntityIDV2({entityId}, {getFlagBits}, response)'
                showApiDebug('auditResult', apiCall, getFlagList, jsonData)

            #--get the list of features for the entity
            entityFeatures = {}
            for ftypeCode in jsonData['RESOLVED_ENTITY']['FEATURES']:
                if ftypeCode in ('REL_ANCHOR', 'REL_POINTER'):
                    continue
                ftypeId = self.ftypeCodeLookup[ftypeCode]['FTYPE_ID']
                if ftypeId not in ftypesUsed:
                    ftypesUsed.append(ftypeId)
                for distinctFeatureRecord in jsonData['RESOLVED_ENTITY']['FEATURES'][ftypeCode]:
                    for featRecord in distinctFeatureRecord['FEAT_DESC_VALUES']:
                        libFeatId = featRecord['LIB_FEAT_ID']
                        entityFeatures[libFeatId] = {}
                        entityFeatures[libFeatId]['ftypeId'] = ftypeId
                        entityFeatures[libFeatId]['ftypeCode'] = ftypeCode
                        entityFeatures[libFeatId]['featDesc'] = featRecord['FEAT_DESC']

            #--get the list of features for each record
            for record in jsonData['RESOLVED_ENTITY']['RECORDS']:
                recordFeatures = {}
                for featRecord in record['FEATURES']:
                    libFeatId = featRecord['LIB_FEAT_ID']
                    if libFeatId in entityFeatures:
                        ftypeId = entityFeatures[libFeatId]['ftypeId']
                        ftypeCode = entityFeatures[libFeatId]['ftypeCode']
                        if ftypeId not in recordFeatures:
                            recordFeatures[ftypeId] = []
                        recordFeatures[ftypeId].append(entityFeatures[libFeatId])

                smallRecord = {}
                smallRecord['DATA_SOURCE'] = record['DATA_SOURCE']
                smallRecord['RECORD_ID'] = record['RECORD_ID']
                smallRecord['features'] = recordFeatures
                recordList.append(smallRecord)


        #--combine the features with the actual audit records
        missingRecord = False
        updatedRecords = []
        for auditRecord in auditRecords:
            if 'data_source' in auditRecord:
                thisRecord = [x for x in recordList if x['RECORD_ID'] == auditRecord['record_id'] and x['DATA_SOURCE'] == auditRecord['data_source']]
            else:
                thisRecord = [x for x in recordList if x['RECORD_ID'] == auditRecord['record_id']]

            if len(thisRecord) != 1:
                auditRecord['features'] = {}
                auditRecord['record_id'] = '** ' + auditRecord['record_id']
                missingRecord = True
            else:
                auditRecord['features'] = thisRecord[0]['features']
            updatedRecords.append(auditRecord)

        #--add the columns to the table format and do the final formatting
        ftypesUsed = sorted(ftypesUsed)
        for ftypeID in ftypesUsed:
            ftypeCode = self.ftypeLookup[ftypeID]['FTYPE_CODE']
            tblColumns.append({'name': ftypeCode, 'width': 50, 'align': 'left'})

        statusSortOrder = {}
        statusSortOrder['same'] = '1'
        statusSortOrder['new negative'] = '2'
        statusSortOrder['new positive'] = '3'
        statusSortOrder['missing'] = '4'

        tblRows = []
        for auditRecord in sorted(updatedRecords, key=lambda k: [statusSortOrder[k['audit_result']], str(k['prior_id']), str(k['newer_id'])]):

            if categoryColors:
                if auditRecord['audit_result'].upper() == 'NEW POSITIVE':
                    auditResultColor = categoryColors['MERGE']
                elif auditRecord['audit_result'].upper() == 'NEW NEGATIVE':
                    auditResultColor = categoryColors['SPLIT']
                elif auditRecord['audit_result'].upper() == 'MISSING':
                    auditResultColor = categoryColors['unknown']
                else:
                    auditResultColor = 'bold'
            else:
                auditResultColor = None
            row = []
            row.append(colorize(auditRecord['data_source'], self.colors['datasource'] if categoryColors else None) if 'data_source' in auditRecord else '')
            row.append(auditRecord['record_id'])
            row.append(auditRecord['prior_id'])
            row.append(auditRecord['prior_score'])
            row.append(colorize(str(auditRecord['newer_id']), self.colors['entityid'] if categoryColors else None))
            row.append(auditRecord['newer_score'])
            row.append(colorize(str(auditRecord['audit_result']), auditResultColor if categoryColors else None))

            for ftypeId in ftypesUsed:
                columnValue = ''
                if ftypeId in auditRecord['features']:
                    columnValue = '\n'.join([x['featDesc'] for x in auditRecord['features'][ftypeId]])
                row.append(columnValue)                

            tblRows.append(row)

        if not categoryColors:
            return tblColumns, tblRows
        else:
            self.renderTable(tblTitle, tblColumns, tblRows)
            return

    # -----------------------------
    def do_entitySizeBreakdown (self,arg):
        '\nDisplays the stats for entities based on their size (how many records they contain).' \
        '\n\nSyntax:' \
        '\n\tentitySizeBreakdown                    (with no parameters displays the overall stats)' \
        '\n\tentitySizeBreakdown = 3                (use =, > or < # to select examples of entities of a certain size)' \
        '\n\tentitySizeBreakdown > 10 review        (to just browse the review items of entities greater than size 10)' \
        '\n\tentitySizeBreakdown = review name+addr (to just browse the name+addr review items of any size)' \
        '\n\nNotes: ' \
        '\n\tReview items are suggestions of records to look at because they contain multiple names, addresses, dobs, etc.' \
        '\n\tThey may be overmatches or they may just be large entities with lots of values.\n'

        if not self.snapshotData or 'ENTITY_SIZE_BREAKDOWN' not in self.snapshotData:
            printWithNewLines('Please load a json file created with G2Snapshot.py to use this command', 'B')
            return

        #--turn esb into a list of size groups if not previously calculated
        if type(self.snapshotData['ENTITY_SIZE_BREAKDOWN']) == dict:
            response = input('\nPerform entity review, first? (yes/no) {note: this may take several minutes} ')            
            reviewRequested = True if response.upper() in ('Y','YES') else False
            self.snapshotData['ENTITY_SIZE_BREAKDOWN'] = self.summarize_entitySizeBreakdown(self.snapshotData['ENTITY_SIZE_BREAKDOWN'], reviewRequested)
            if reviewRequested:
                try: 
                    with open(self.snapshotFile, 'w') as f:
                        json.dump(self.snapshotData, f)
                except IOError as err:
                    print('Could not save review to %s ...' % self.snapshotFile)
                    input('Press any key ...')

        if 'ENTITY_SIZE_GROUP' not in self.snapshotData['ENTITY_SIZE_BREAKDOWN'][0]:
            printWithNewLines('The statistics loaded contain an older entity size structure this viewer cannot display', 'S')
            printWithNewLines('Please take a new snapshot with G2Snapshot.py to re-compute with the latest entity size breakdown structure', 'E')
            return

        #--display the summary if no arguments
        if not arg:
            
            tblTitle = 'Entity Size Breakdown from %s' % self.snapshotFile
            tblColumns = []
            tblColumns.append({'name': 'Entity Size', 'width': 10, 'align': 'center'})
            tblColumns.append({'name': 'Entity Count', 'width': 10, 'align': 'center'})
            tblColumns.append({'name': 'Review Count', 'width': 10, 'align': 'center'})
            tblColumns.append({'name': 'Review Features', 'width': 75, 'align': 'left'})

            tblRows = []
            for entitySizeData in sorted(self.snapshotData['ENTITY_SIZE_BREAKDOWN'], key=lambda k: k['ENTITY_SIZE'], reverse = True):
                row = []
                row.append('%s' % (entitySizeData['ENTITY_SIZE_GROUP']))
                row.append('%s' % (entitySizeData['ENTITY_COUNT'], ))
                row.append('%s' % (entitySizeData['REVIEW_COUNT'], ))
                row.append(' | '.join(sorted(entitySizeData['REVIEW_FEATURES'])))
                tblRows.append(row)
            self.renderTable(tblTitle, tblColumns, tblRows)

        else:
            sign = '='
            size = 0
            reviewTag = False
            reviewFeatures = []
            argList = arg.split()
            for token in argList:
                if token[0:2] in ('>=', '<='):
                    sign = token[0:2]
                    if len(token) > 2 and token[2:].isnumeric():
                        size = int(token[2:])
                elif token[0:1] in ('>', '<', '='):
                    sign = token[0:1]
                    if len(token) > 1 and token[1:].isnumeric():
                        size = int(token[1:])
                elif token.isnumeric():
                    size = int(token)
                elif token.upper() == 'REVIEW':
                    reviewTag = True
                else:
                    reviewFeatures.append(token.upper())

            if not size:
                size = 1
                sign = '>'

            sampleRecords = []
            for entitySizeData in self.snapshotData['ENTITY_SIZE_BREAKDOWN']:

                #--add these entities if they satisfy the entity size argument 
                if sign in ('=', '>=', '<=') and entitySizeData['ENTITY_SIZE'] == size:
                    theseRecords = entitySizeData['SAMPLE_ENTITIES']
                elif sign in ('<', '<=') and entitySizeData['ENTITY_SIZE'] < size:
                    theseRecords = entitySizeData['SAMPLE_ENTITIES']
                elif sign in ('>', '>=') and entitySizeData['ENTITY_SIZE'] > size:
                    theseRecords = entitySizeData['SAMPLE_ENTITIES']
                else:
                    continue

                #--filter for review features
                if reviewTag or reviewFeatures:
                    reviewRecords = []
                    for entityInfo in theseRecords:
                        if 'REVIEW_FEATURES' not in entityInfo:
                            continue
                        if reviewFeatures: 
                            reviewCriteriaNotMet = False
                            for ftypeCode in reviewFeatures:
                                if ftypeCode not in entityInfo['REVIEW_FEATURES']:
                                    reviewCriteriaNotMet = True
                                    break
                            if reviewCriteriaNotMet:
                                continue
                        reviewRecords.append(entityInfo)
                    theseRecords = reviewRecords

                sampleRecords.extend(theseRecords) 

            if len(sampleRecords) == 0:
                print('\nNo records found for entitySizeBreakdown %s, command syntax: %s \n' % (arg, '\n\n' + self.do_entitySizeBreakdown.__doc__[1:]))
            else:

                currentSample = 0
                while True:
                    exportRecords = [sampleRecords[currentSample]['ENTITY_ID']]

                    self.currentReviewList = 'ENTITY SIZE %s' % sampleRecords[currentSample]['ENTITY_SIZE']
                    if 'REVIEW_FEATURES' in sampleRecords[currentSample]:
                        reviewItems = []
                        for ftypeCode in sampleRecords[currentSample]['REVIEW_FEATURES']:
                            reviewItems.append('%s (%s)' % (ftypeCode, sampleRecords[currentSample][ftypeCode]))
                        self.currentReviewList += ' - REVIEW FOR: ' + ' | '.join(reviewItems)

                    returnCode = self.do_get(exportRecords[0])
                    if returnCode != 0:
                        printWithNewLines('The statistics loaded are out of date for this entity','E')

                    while True:
                        reply = input('Select (P)revious, (N)ext, (S)croll, (D)etail, (W)hy, (E)xport, (Q)uit ...')
                        if reply:
                            removeFromHistory()
                        else:
                            break

                        if reply.upper().startswith('R'): #--reload
                            break
                        elif reply.upper().startswith('P'): #--previous
                            if currentSample == 0:
                                printWithNewLines('no prior records!', 'B')
                            else:
                                currentSample = currentSample - 1
                                break
                        elif reply.upper().startswith('N'): #--next
                            if currentSample == len(sampleRecords) - 1:
                                printWithNewLines('no more records!', 'B')
                            else:
                                currentSample += 1
                                break
                        elif reply.upper().startswith('Q'): #--quit
                            break

                        #--special actions 
                        elif reply.upper().startswith('S'): #--scrolling view
                            self.do_scroll('')
                        elif reply.upper().startswith('D'): #--detail view
                            self.do_get('detail ' + ','.join(exportRecords))
                        elif reply.upper().startswith('W'): #--why view
                            self.do_why(','.join(exportRecords))
                        elif reply.upper().startswith('H'): #--how view
                            self.do_how(','.join(exportRecords))
                        elif reply.upper().startswith('E'): #--export
                            fileName = None
                            if 'TO' in reply.upper():
                                fileName = reply[reply.upper().find('TO') + 2:].strip()
                            else:                            
                                fileName = '%s.json' % '-'.join(exportRecords)
                                #fileName = os.path.join(os.path.expanduser("~"), fileName)
                            self.do_export(','.join(exportRecords) + 'to ' + fileName)

                    if reply.upper().startswith('Q'):
                        break
                self.currentReviewList = None

    # -----------------------------
    def summarize_entitySizeBreakdown (self, rawEntitySizeData, reviewRequested):

        if reviewRequested:
            reviewCount = sum([len(rawEntitySizeData[size]['SAMPLE']) for size in rawEntitySizeData.keys()])
            print('\nreviewing %s entities ... ' % reviewCount)

        progressCnt = 0
        newEntitySizeData = {}
        for entitySize in sorted([int(x) for x in rawEntitySizeData.keys()]):
            strEntitySize = str(entitySize)
            if entitySize < 10:
                entitySizeLevel = entitySize
            elif entitySize < 100:
                entitySizeLevel = int(entitySize/10) * 10
            else:
                entitySizeLevel = int(entitySize/100) * 100

            if entitySizeLevel not in newEntitySizeData:
                newEntitySizeData[entitySizeLevel] = {}
                newEntitySizeData[entitySizeLevel]['ENTITY_COUNT'] = 0
                newEntitySizeData[entitySizeLevel]['SAMPLE_ENTITIES'] = []
                newEntitySizeData[entitySizeLevel]['REVIEW_COUNT'] = 0
                newEntitySizeData[entitySizeLevel]['REVIEW_FEATURES'] = []
            newEntitySizeData[entitySizeLevel]['ENTITY_COUNT'] += rawEntitySizeData[strEntitySize]['COUNT']

            for entityID in rawEntitySizeData[strEntitySize]['SAMPLE']:
                sampleRecord = {'ENTITY_SIZE': entitySize, 'ENTITY_ID': str(entityID)}
                if reviewRequested:
                    reviewInfo = self.review_ESBSample(sampleRecord)
                    sampleRecord.update(reviewInfo)
                    if 'REVIEW_FEATURES' in reviewInfo:
                        newEntitySizeData[entitySizeLevel]['REVIEW_COUNT'] += 1
                        for featureCode in reviewInfo['REVIEW_FEATURES']:
                            if featureCode not in newEntitySizeData[entitySizeLevel]['REVIEW_FEATURES']:
                                newEntitySizeData[entitySizeLevel]['REVIEW_FEATURES'].append(featureCode)
                    progressCnt += 1
                    if progressCnt % 1000 == 0:
                        print('%s entities reviewed' % progressCnt)

                #--review it here
                newEntitySizeData[entitySizeLevel]['SAMPLE_ENTITIES'].append(sampleRecord)

        newEntitySizeList = []
        for entitySize in sorted(newEntitySizeData.keys()):
            entitySizeRecord = newEntitySizeData[entitySize]
            entitySizeRecord['ENTITY_SIZE'] = int(entitySize)
            entitySizeRecord['ENTITY_SIZE_GROUP'] = str(entitySize) + ('+' if int(entitySize) >= 10 else '')
            newEntitySizeList.append(entitySizeRecord)

        if reviewRequested:
            print('%s entities reviewed, complete' % progressCnt)


        return newEntitySizeList

    # -----------------------------
    def review_ESBSample (self, sampleRecord):
        entitySize = sampleRecord['ENTITY_SIZE']
        entityID = sampleRecord['ENTITY_ID']
        if entitySize == 1:
            return sampleRecord

        #--set maximums based on entity size
        if entitySize <= 3: #--super small
            maxExclusiveCnt = 1
            maxNameCnt = 2
            maxAddrCnt = 2
        elif entitySize <= 10: #--small
            maxExclusiveCnt = 1
            maxNameCnt = 3
            maxAddrCnt = 3
        elif entitySize <= 50: #--medium
            maxExclusiveCnt = 1
            maxNameCnt = 10
            maxAddrCnt = 10
        else: #--large
            maxExclusiveCnt = 1 #--large
            maxNameCnt = 25
            maxAddrCnt = 25

        #--get the entity
        try: 
            response = bytearray()
            retcode = g2Engine.getEntityByEntityIDV2(int(entityID), self.computeApiFlags(['G2_ENTITY_INCLUDE_REPRESENTATIVE_FEATURES']), response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print(str(err))
            return sampleRecord
        try: jsonData = json.loads(response)
        except:
            print('warning: entity %s response=[%s]' % (entityID, response))
            return sampleRecord

        #print('entityID %s, size %s' % (entityID, entitySize))

        featureInfo = {}
        for ftypeCode in jsonData['RESOLVED_ENTITY']['FEATURES']:
            distinctFeatureCount = 0
            for distinctFeature in jsonData['RESOLVED_ENTITY']['FEATURES'][ftypeCode]:
                if ftypeCode == 'GENDER' and distinctFeature['FEAT_DESC'] not in ('M', 'F'): #--don't count invalid genders
                    continue
                distinctFeatureCount += 1
            if ftypeCode not in featureInfo:
                featureInfo[ftypeCode] = 0
            featureInfo[ftypeCode] += distinctFeatureCount

        reviewFeatures = []
        for ftypeCode in featureInfo:
            distinctFeatureCount = featureInfo[ftypeCode]

            #--watch lists have more multiple features per record like 5 dobs and 10 names!
            if distinctFeatureCount > entitySize:
                continue

            frequency = self.ftypeCodeLookup[ftypeCode]['FTYPE_FREQ']
            exclusive = str(self.ftypeCodeLookup[ftypeCode]['FTYPE_EXCL']).upper() in ('1', 'Y', 'YES')

            needsReview = False
            if exclusive and distinctFeatureCount > maxExclusiveCnt:
                needsReview = True
            elif ftypeCode == 'NAME' and distinctFeatureCount > maxNameCnt:
                needsReview = True
            elif ftypeCode == 'ADDRESS' and distinctFeatureCount > maxAddrCnt:
                needsReview = True

            if needsReview: 
                reviewFeatures.append(ftypeCode)

        if reviewFeatures:
            featureInfo['REVIEW_FEATURES'] = reviewFeatures
 
        return featureInfo

    # -----------------------------
    def do_dataSourceSummary (self, arg):
        '\nDisplays the stats for the different match levels within each data source.' \
        '\n\nSyntax:' \
        '\n\tdataSourceSummary (with no parameters displays the overall stats)' \
        '\n\tdataSourceSummary <dataSourceCode> <matchLevel>  where 0=Singletons, 1=Duplicates, 2=Ambiguous, 3=Possibles, 4=Relationships\n'

        if not self.snapshotData or 'DATA_SOURCES' not in self.snapshotData:
            printWithNewLines('Please load a json file created with G2Snapshot.py to use this command', 'B')
            return

        #--display the summary if no arguments
        if not arg:

            tblTitle = 'Data Source Summary from %s' % self.snapshotFile
            tblColumns = []
            tblColumns.append({'name': 'Data Source', 'width': 25, 'align': 'left'})
            tblColumns.append({'name': 'Records', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Entities', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Compression', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Singletons', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Duplicates', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Ambiguous', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Possibles', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Relationships', 'width': 15, 'align': 'right'})

            tblRows = []
            for dataSource in sorted(self.snapshotData['DATA_SOURCES']):
                row = []
                row.append(colorize(dataSource, self.colors['datasource']))
                row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource]['RECORD_COUNT']) if 'RECORD_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource] else 0)
                row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource]['ENTITY_COUNT']) if 'ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource] else 0)
                row.append(self.snapshotData['DATA_SOURCES'][dataSource]['COMPRESSION'] if 'COMPRESSION' in self.snapshotData['DATA_SOURCES'][dataSource] else 0)
                row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource]['SINGLE_COUNT']) if 'SINGLE_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource] else 0)
                if self.current_settings['statistic_level'] == 'record':
                    row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource].get('DUPLICATE_RECORD_COUNT', 0)))
                    row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource].get('AMBIGUOUS_MATCH_RECORD_COUNT', 0)))
                    row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource].get('POSSIBLE_MATCH_RECORD_COUNT', 0)))
                    row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource].get('POSSIBLY_RELATED_RECORD_COUNT', 0)))
                else:
                    row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource]['DUPLICATE_ENTITY_COUNT']) if 'DUPLICATE_ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource] else 0)
                    row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource]['AMBIGUOUS_MATCH_ENTITY_COUNT']) if 'AMBIGUOUS_MATCH_ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource] else 0)
                    row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource]['POSSIBLE_MATCH_ENTITY_COUNT']) if 'POSSIBLE_MATCH_ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource] else 0)
                    row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource]['POSSIBLY_RELATED_ENTITY_COUNT']) if 'POSSIBLY_RELATED_ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource] else 0)

                tblRows.append(row)
            
            if not arg:
                self.renderTable(tblTitle, tblColumns, tblRows)
            else:
                return tblColumns, tblRows

        else:

            argTokens = arg.split()
            if len(argTokens) != 2:
                print('\nMissing argument(s) for %s, command syntax: %s \n' % ('do_dataSourceSummary', '\n\n' + self.do_dataSourceSummary.__doc__[1:]))
                return

            dataSource = argTokens[0].upper()
            if dataSource not in self.snapshotData['DATA_SOURCES']:
                printWithNewLines('%s is not a valid data source' % dataSource, 'B')
                return

            matchLevel = argTokens[1].upper()
            matchLevelCode = None
            for matchLevelParameter in self.validMatchLevelParameters:
                if matchLevel.startswith(matchLevelParameter):
                    matchLevelCode = self.validMatchLevelParameters[matchLevelParameter]
                    break
            if not matchLevelCode:
                printWithNewLines('%s is not a valid match level' % matchLevel, 'B')
                return

            try: sampleRecords = [k for k in self.snapshotData['DATA_SOURCES'][dataSource][matchLevelCode]]
            except:
                printWithNewLines('no samples found for %s' % arg, 'B')
                return

            if len(sampleRecords) == 0:
                printWithNewLines('no entities to display!', 'B')
            else:

                self.currentReviewList = 'DATA SOURCE SUMMARY FOR: %s (%s)' % (dataSource, matchLevelCode) 
                currentSample = 0
                while True:
                    if matchLevelCode in ('SINGLE_SAMPLE', 'DUPLICATE_SAMPLE'):
                        exportRecords = [str(sampleRecords[currentSample])]
                        returnCode = self.do_get(exportRecords[0], dataSourceFilter=[dataSource])
                    else:
                        exportRecords = sampleRecords[currentSample].split()[:2]
                        if matchLevelCode == 'AMBIGUOUS_MATCH_SAMPLE':
                            ambiguousList =self.getAmbiguousEntitySet(exportRecords[0]) #--is this the ambiguous entity
                            if ambiguousList:
                                exportRecords = ambiguousList
                            else:
                                ambiguousList =self.getAmbiguousEntitySet(exportRecords[1]) #--or is this the ambiguous entity
                                if ambiguousList:
                                    exportRecords = ambiguousList
                                else:
                                    pass #--if its neither, just show the original two entities
                        returnCode = self.do_compare(','.join(exportRecords), dataSourceFilter=[dataSource])
                    if returnCode != 0:
                        printWithNewLines('The statistics loaded are out of date for this record!','E')
                    while True:
                        if matchLevelCode in ('SINGLE_SAMPLE', 'DUPLICATE_SAMPLE'):
                            reply = input('Select (P)revious, (N)ext, (S)croll, (D)etail, (W)hy, (E)xport, (Q)uit ...')
                        else:
                            reply = input('Select (P)revious, (N)ext, (S)croll, (W)hy, (E)xport, (Q)uit ...')
          
                        if reply:
                            removeFromHistory()
                        else:
                            break

                        if reply.upper().startswith('R'): #--reload
                            break
                        elif reply.upper().startswith('P'): #--previous
                            if currentSample == 0:
                                printWithNewLines('no prior records!', 'B')
                            else:
                                currentSample = currentSample - 1
                                break
                        elif reply.upper().startswith('N'): #--next
                            if currentSample == len(sampleRecords) - 1:
                                printWithNewLines('no more records!', 'B')
                            else:
                                currentSample += 1
                                break
                        elif reply.upper().startswith('Q'): #--quit
                            break

                        #--special actions 
                        elif reply.upper().startswith('S'): #--scrolling view
                            self.do_scroll('')
                        elif reply.upper().startswith('D') and matchLevelCode in ('SINGLE_SAMPLE', 'DUPLICATE_SAMPLE'): #--detail view
                            self.do_get('detail ' + ','.join(exportRecords))
                        elif reply.upper().startswith('W'): #--why view
                            self.do_why(','.join(exportRecords))
                        elif reply.upper().startswith('E'): #--export
                            fileName = None
                            if 'TO' in reply.upper():
                                fileName = reply[reply.upper().find('TO') + 2:].strip()
                            else:                            
                                fileName = '%s.json' % '-'.join(exportRecords)
                                #fileName = os.path.join(os.path.expanduser("~"), fileName)
                            self.do_export(','.join(exportRecords) + 'to ' + fileName)

                    if reply.upper().startswith('Q'):
                        break
            self.currentReviewList = None

    # -----------------------------
    def complete_dataSourceSummary(self, text, line, begidx, endidx):
        before_arg = line.rfind(" ", 0, begidx)
        #if before_arg == -1:
        #    return # arg not found

        fixed = line[before_arg+1:begidx]  # fixed portion of the arg
        arg = line[before_arg+1:endidx]

        spaces = line.count(' ')
        if spaces <= 1:
            possibles = []
            if self.snapshotData:
                for dataSource in sorted(self.snapshotData['DATA_SOURCES']):
                    possibles.append(dataSource)
        elif spaces == 2:
            possibles = ['singles', 'duplicates', 'ambiguous', 'possibles', 'relationships' ]
        else:
            possibles = []

        return [i for i in possibles if i.lower().startswith(arg.lower())]

    # -----------------------------
    def do_crossSourceSummary (self,arg):
        '\nDisplays the stats for the different match levels across data sources.' \
        '\n\nSyntax:' \
        '\n\tcrossSourceSummary (with no parameters displays the overall stats)' \
        '\n\tcrossSourceSummary <dataSource1> (displays the cross matches for that data source only)' \
        '\n\tcrossSourceSummary <dataSource1> <dataSource2> <matchLevel> where 1=Matches, 2=Ambiguous, 3=Possibles, 4=Relationships\n'
 
        if not self.snapshotData or 'DATA_SOURCES' not in self.snapshotData:
            print('\nPlease load a json file created with G2Snapshot.py to use this command\n')
            return

        #--display the summary if no arguments
        if not arg or len(arg.split()) == 1:

            tblTitle = 'Cross Source Summary from %s' % self.snapshotFile
            tblColumns = []
            tblColumns.append({'name': 'Data Source1', 'width': 25, 'align': 'left'})
            tblColumns.append({'name': 'Data Source2', 'width': 25, 'align': 'left'})
            tblColumns.append({'name': 'Matches', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Ambiguous', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Possibles', 'width': 15, 'align': 'right'})
            tblColumns.append({'name': 'Relationships', 'width': 15, 'align': 'right'})

            tblRows = []
            for dataSource1 in sorted(self.snapshotData['DATA_SOURCES']):
                if arg and dataSource1 != arg.upper():
                    continue
                for dataSource2 in sorted(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES']):

                    #for key in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]:
                    #    if type(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2][key]) != list:
                    #        print ('%s = %s' % (key, self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2][key]))

                    row = []
                    row.append(colorize(dataSource1, self.colors['datasource']))
                    row.append(colorize(dataSource2, self.colors['datasource']))

                    if self.current_settings['statistic_level'] == 'record':
                        row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]['MATCH_RECORD_COUNT']) if 'MATCH_RECORD_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2] else 0)
                        row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]['AMBIGUOUS_MATCH_RECORD_COUNT']) if 'AMBIGUOUS_MATCH_RECORD_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2] else 0)
                        row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]['POSSIBLE_MATCH_RECORD_COUNT']) if 'POSSIBLE_MATCH_RECORD_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2] else 0)
                        row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]['POSSIBLY_RELATED_RECORD_COUNT']) if 'POSSIBLY_RELATED_RECORD_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2] else 0)
                    else:
                        row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]['MATCH_ENTITY_COUNT']) if 'MATCH_ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2] else 0)
                        row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]['AMBIGUOUS_MATCH_ENTITY_COUNT']) if 'AMBIGUOUS_MATCH_ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2] else 0)
                        row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]['POSSIBLE_MATCH_ENTITY_COUNT']) if 'POSSIBLE_MATCH_ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2] else 0)
                        row.append(fmtStatistic(self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2]['POSSIBLY_RELATED_ENTITY_COUNT']) if 'POSSIBLY_RELATED_ENTITY_COUNT' in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2] else 0)

                    tblRows.append(row)

            self.renderTable(tblTitle, tblColumns, tblRows)

        else:

            argTokens = arg.split()
            if len(argTokens) != 3:
                print('\nMissing argument(s) for %s, command syntax: %s \n' % ('do_crossSourceSummary', '\n\n' + self.do_crossSourceSummary.__doc__[1:]))
                return

            dataSource1 = argTokens[0].upper()
            if dataSource1 not in self.snapshotData['DATA_SOURCES']:
                printWithNewLines('%s is not a valid data source' % dataSource1, 'B')
                return

            dataSource2 = argTokens[1].upper()
            if dataSource2 not in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES']:
                printWithNewLines('%s is not a matching data source' % dataSource2, 'B')
                return

            matchLevel = argTokens[2].upper()
            matchLevelCode = None
            for matchLevelParameter in self.validMatchLevelParameters:
                if matchLevel.startswith(matchLevelParameter):
                    matchLevelCode = self.validMatchLevelParameters[matchLevelParameter]
                    break

            if not matchLevelCode:
                printWithNewLines('%s is not a valid match level' % matchLevel, 'B')
                return

            #--duplicates are matches for cross source
            if matchLevelCode == 'DUPLICATE_SAMPLE':
                matchLevelCode = 'MATCH_SAMPLE'

            try: sampleRecords = [k for k in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2][matchLevelCode]]
            except:
                printWithNewLines('no samples found for %s' % arg, 'B')
                return

            if len(sampleRecords) == 0:
                printWithNewLines('no entities to display!', 'B')
            else:

                self.currentReviewList = 'CROSS SOURCE SUMMARY for: %s-%s  (%s)' % (dataSource1, dataSource2, matchLevelCode) 
                currentSample = 0
                while True:

                    if matchLevelCode in ('MATCH_SAMPLE'):
                        exportRecords = [str(sampleRecords[currentSample])]
                        returnCode = self.do_get(exportRecords[0], dataSourceFilter=[dataSource1, dataSource2])
                    else:
                        exportRecords = sampleRecords[currentSample].split()[:2]
                        if matchLevelCode == 'AMBIGUOUS_MATCH_SAMPLE':
                            ambiguousList =self.getAmbiguousEntitySet(exportRecords[0]) #--is this the ambiguous entity
                            if ambiguousList:
                                exportRecords = ambiguousList
                            else:
                                ambiguousList =self.getAmbiguousEntitySet(exportRecords[1]) #--or is this the ambiguous entity
                                if ambiguousList:
                                    exportRecords = ambiguousList
                                else:
                                    pass #--if its neither, just show the original two entities
                        returnCode = self.do_compare(','.join(exportRecords), dataSourceFilter=[dataSource1, dataSource2])

                    if returnCode != 0:
                        printWithNewLines('The statistics loaded are out of date for this entity','E')

                    while True:
                        if matchLevelCode in ('MATCH_SAMPLE'):
                            reply = input('Select (P)revious, (N)ext, (S)croll, (D)etail, (W)hy, (E)xport, (Q)uit ...')
                        else:
                            reply = input('Select (P)revious, (N)ext, (S)croll, (W)hy, (E)xport, (Q)uit ...')

                        if reply:
                            removeFromHistory()
                        else:
                            break

                        if reply.upper().startswith('R'): #--reload
                            break
                        elif reply.upper().startswith('P'): #--previous
                            if currentSample == 0:
                                printWithNewLines('no prior records!', 'B')
                            else:
                                currentSample = currentSample - 1
                                break
                        elif reply.upper().startswith('N'): #--next
                            if currentSample == len(sampleRecords) - 1:
                                printWithNewLines('no more records!', 'B')
                            else:
                                currentSample += 1
                                break
                        elif reply.upper().startswith('Q'): #--quit
                            break

                        #--special actions 
                        elif reply.upper().startswith('S'): #--scrolling view
                            self.do_scroll('')
                        elif reply.upper().startswith('D') and matchLevelCode in ('MATCH_SAMPLE'): #--detail view
                            self.do_get('detail ' + ','.join(exportRecords))
                        elif reply.upper().startswith('W'): #--why view
                            self.do_why(','.join(exportRecords))
                        elif reply.upper().startswith('E'): #--export
                            fileName = None
                            if 'TO' in reply.upper():
                                fileName = reply[reply.upper().find('TO') + 2:].strip()
                            else:                            
                                fileName = '%s.json' % '-'.join(exportRecords)
                                #fileName = os.path.join(os.path.expanduser("~"), fileName)
                            self.do_export(','.join(exportRecords) + 'to ' + fileName)

                    if reply.upper().startswith('Q'):
                        break
                self.currentReviewList = None

    # -----------------------------
    def complete_crossSourceSummary(self, text, line, begidx, endidx):
        before_arg = line.rfind(" ", 0, begidx)
        if before_arg == -1:
            return # arg not found

        fixed = line[before_arg+1:begidx]  # fixed portion of the arg
        arg = line[before_arg+1:endidx]

        spaces = line.count(' ')
        if spaces <= 1:
            possibles = []
            if self.snapshotData:
                for dataSource in sorted(self.snapshotData['DATA_SOURCES']):
                    possibles.append(dataSource)
        elif spaces == 2:
            possibles = []
            if self.snapshotData:
                for dataSource in sorted(self.snapshotData['DATA_SOURCES']):
                    possibles.append(dataSource)
        elif spaces == 3:
            possibles = ['singles', 'duplicates', 'ambiguous', 'possibles', 'relationships' ]
        else:
            possibles = []

        return [i for i in possibles if i.lower().startswith(arg.lower())]

    # -----------------------------
    def do_search(self,arg):
        '\nSearches for entities by their attributes.' \
        '\n\nSyntax:' \
        '\n\tsearch Joe Smith (without a json structure performs a search on name alone)' \
        '\n\tsearch {"name_full": "Joe Smith"}' \
        '\n\tsearch {"name_org": "ABC Company"}' \
        '\n\tsearch {"name_last": "Smith", "name_first": "Joe", "date_of_birth": "1992-12-10"}' \
        '\n\tsearch {"name_org": "ABC Company", "addr_full": "111 First St, Anytown, USA 11111"}' \
        '\n\nNotes: ' \
        '\n\tSearching by name alone may not locate a specific entity.' \
        '\n\tTry adding a date of birth, address, or phone number if not found by name alone.\n'

        if not argCheck('do_search', arg, self.do_search.__doc__):
            return

        try:
            parmData = dictKeysUpper(json.loads(arg)) if arg.startswith('{') else {"PERSON_NAME_FULL": arg, "ORGANIZATION_NAME_ORG": arg}
        except (ValueError, KeyError) as e:
            argError(arg, e)
        else:

            print('')
            print('Searching ...')
            searchJson = parmData
            searchFlagList = []
            if apiVersion['VERSION'][0:1] > '1':
                searchFlagList.append('G2_SEARCH_INCLUDE_ALL_ENTITIES')
                searchFlagList.append('G2_SEARCH_INCLUDE_FEATURE_SCORES')
                searchFlagList.append('G2_ENTITY_INCLUDE_ENTITY_NAME')
                searchFlagList.append('G2_ENTITY_INCLUDE_RECORD_DATA')
                searchFlagList.append('G2_SEARCH_INCLUDE_STATS')
                searchFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
                searchFlagList.append('G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO')
            else:
                searchFlagList.append('G2_SEARCH_BY_ATTRIBUTES_DEFAULT_FLAGS')
            searchFlagBits = self.computeApiFlags(searchFlagList)

            try: 
                response = bytearray()
                retcode = g2Engine.searchByAttributesV2(json.dumps(searchJson), searchFlagBits, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print(json.dumps(searchJson, indent=4))
                print(str(err))
                return
            jsonResponse = json.loads(response)
            if debugOutput:
                showDebug('searchMessage', searchJson)
                apiCall = f'searchByAttributesV2(searchMessage, {searchFlagBits}, response)'
                showApiDebug('search', apiCall, searchFlagList, jsonResponse)

                
            #--constants for descriptions and sort orders
            dataSourceOrder = [] #--place your data sources here!

            tblTitle = 'Search Results'
            tblColumns = []
            tblColumns.append({'name': 'Index', 'width': 5, 'align': 'center'})
            tblColumns.append({'name': 'Entity ID', 'width': 15, 'align': 'center'})
            tblColumns.append({'name': 'Entity Name', 'width': 75, 'align': 'left'})
            tblColumns.append({'name': 'Data Sources', 'width': 50, 'align': 'left'})
            tblColumns.append({'name': 'Match Key', 'width': 50, 'align': 'left'})
            tblColumns.append({'name': 'Match Score', 'width': 15, 'align': 'center'})
            tblColumns.append({'name': 'Relationships', 'width': 15, 'align': 'left'})

            matchList = []
            searchIndex = 0
            for resolvedEntityBase in jsonResponse['RESOLVED_ENTITIES']:
                resolvedEntity = resolvedEntityBase['ENTITY']['RESOLVED_ENTITY']
                resolvedEntityMatchInfo = resolvedEntityBase['MATCH_INFO']
                searchIndex += 1

                #--create a list of data sources we found them in
                dataSources = {}
                for record in resolvedEntity['RECORDS']:
                    dataSource = record['DATA_SOURCE']
                    if dataSource not in dataSources:
                        dataSources[dataSource] = [record['RECORD_ID']]
                    else:
                        dataSources[dataSource].append(record['RECORD_ID'])

                dataSourceList = []
                for dataSource in dataSources:
                    if len(dataSources[dataSource]) == 1:
                        dataSourceList.append(colorize(dataSource, self.colors['datasource']) + ': ' + dataSources[dataSource][0])
                    else:
                        dataSourceList.append(colorize(dataSource, self.colors['datasource'])  + ': ' + str(len(dataSources[dataSource])) + ' records')

                #relatedEntityCount = len(resolvedEntityBase['ENTITY']['RELATED_ENTITIES'] if 'RELATED_ENTITIES' in resolvedEntityBase['ENTITY'] else 0)
                disclosedCount = 0
                derivedCount = 0
                for relationship in resolvedEntityBase['ENTITY']['RELATED_ENTITIES'] if 'RELATED_ENTITIES' in resolvedEntityBase['ENTITY'] else []:
                    if relationship['IS_DISCLOSED'] > 0:
                        disclosedCount += 1
                    else:
                        derivedCount += 1
                relationshipLines = []
                if derivedCount > 0:
                    relationshipLines.append(f'Derived: {derivedCount} ')
                if disclosedCount > 0:
                    relationshipLines.append(f'Disclosed: {disclosedCount}')

                #--determine the matching criteria
                matchLevel = self.searchMatchLevels[resolvedEntityMatchInfo['MATCH_LEVEL']]
                matchKey = resolvedEntityMatchInfo['MATCH_KEY']
                ruleCode = resolvedEntityMatchInfo['ERRULE_CODE']
                #--scoring
                bestScores = {}
                bestScores['NAME'] = {}
                bestScores['NAME']['score'] = 0
                bestScores['NAME']['value'] = ''
                for featureCode in resolvedEntityMatchInfo['FEATURE_SCORES']:
                    for scoreRecord in resolvedEntityMatchInfo['FEATURE_SCORES'][featureCode]:
                        if featureCode == 'NAME':
                            if 'BT_FN' in scoreRecord:
                                scoreCode = 'BT_FN'
                            else: 
                                scoreCode = 'GNR_FN'
                        else: 
                            scoreCode = 'FULL_SCORE'
                        matchingScore= scoreRecord[scoreCode]
                        matchingValue = scoreRecord['CANDIDATE_FEAT']
                        if featureCode not in bestScores:
                            bestScores[featureCode] = {}
                            bestScores[featureCode]['score'] = 0
                            bestScores[featureCode]['value'] = 'n/a'
                        if matchingScore > bestScores[featureCode]['score']:
                            bestScores[featureCode]['score'] = matchingScore
                            bestScores[featureCode]['value'] = matchingValue

                #--perform scoring (use stored match_score if not overridden in the mapping document)
                matchedScore = bestScores['NAME']['score']
                matchedName = bestScores['NAME']['value']

                weightedScores = {}
                for featureCode in bestScores:
                    weightedScores[featureCode] = {}
                    weightedScores[featureCode]['threshold'] = 0
                    weightedScores[featureCode]['+weight'] = 100
                    weightedScores[featureCode]['-weight'] = 0
                    #if scoredFeatureCount > 1:
                    
                matchScore = 0
                for featureCode in bestScores:
                    if featureCode in weightedScores:
                        if bestScores[featureCode]['score'] >= weightedScores[featureCode]['threshold']:
                            matchScore += int(round(bestScores[featureCode]['score'] * (weightedScores[featureCode]['+weight'] / 100),0))
                        elif '-weight' in weightedScores[featureCode]:
                            matchScore += -weightedScores[featureCode]['-weight'] #--actual score does not matter if below the threshold

                #--create the possible match entity one-line summary
                row = []
                row.append(str(searchIndex)) #--note this gets re-ordered below
                row.append(str(resolvedEntity['ENTITY_ID']))
                row.append(resolvedEntity['ENTITY_NAME'] + (('\n' + ' aka: ' + matchedName) if matchedName and matchedName != resolvedEntity['ENTITY_NAME'] else ''))
                row.append('\n'.join(dataSourceList))
                matchData = {}
                matchData['matchKey'] = matchKey
                matchData['ruleCode'] = self.getRuleDesc(ruleCode)
                row.append(formatMatchData(matchData, self.colors))
                row.append(matchScore)
                row.append('\n'.join(relationshipLines))
                matchList.append(row)

            if len(matchList) == 0:
                print()
                if 'SEARCH_STATISTICS' in jsonResponse:

                    if jsonResponse['SEARCH_STATISTICS'][0]['CANDIDATE_KEYS']['SUMMARY']['FOUND'] > 0:
                        print('\tOne or more entities were found but did not score high enough to be returned')
                        print('\tPlease include additional or more complete attributes in your search')
                    elif jsonResponse['SEARCH_STATISTICS'][0]['CANDIDATE_KEYS']['SUMMARY']['GENERIC'] > 0:
                        print('\tToo many entities would be returned')
                        print('\tPlease include additional attributes to narrow the search results')
                    elif jsonResponse['SEARCH_STATISTICS'][0]['CANDIDATE_KEYS']['SUMMARY']['NOT_FOUND'] > 0:
                        print('\tNo entities at all were found')
                        print('\tPlease search by other attributes for this entity if you feel it should exist')
                    else:
                        print('\tNo search keys were even generated')
                        print('\tPlease search by other attributes')

                else: #--older versions do not have statistics
                    print('\tNo matches found or there were simply too many to return')
                    print('\tPlease include additional search parameters if you feel this entity is in the database')
            else:

                #--sort the list by match score descending
                matchList = sorted(matchList, key=lambda x: x[5], reverse=True)

                #--store the last search result and colorize
                self.lastSearchResult = []
                for i in range(len(matchList)):
                    self.lastSearchResult.append(matchList[i][1])
                    matchList[i][0] = str(i+1)
                    matchList[i][1] = colorize(matchList[i][1], self.colors['entityid'])
                    matchList[i][2] = matchList[i][2]
                self.renderTable(tblTitle, tblColumns, matchList)

            print('')

    # -----------------------------
    def do_get(self, arg, **kwargs):

        '\nDisplays a particular entity by entity_id or by data_source and record_id.' \
        '\n\nSyntax:' \
        '\n\tget <entity_id>' \
        '\n\tget <dataSource> <recordID>' \
        '\n\tget search <search index>' \
        '\n\tget detail <entity_id>' \
        '\n\tget detail <dataSource> <recordID>' \
        '\n\nNotes: ' \
        '\n\tget search is a shortcut to the entity ID at the search index provided. Must be valid for the last search performed' \
        '\n\tget detail displays every record for the entity while a get alone displays a summary of the entity by dataSource.\n'

        if not argCheck('do_get', arg, self.do_get.__doc__):
            return

        #--no return code if called direct
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'

        #--get possible data source list
        if 'dataSourceFilter' in kwargs and self.current_settings['data_source_suppression'] == 'on':
            dataSourceFilter = kwargs['dataSourceFilter']
        else:
            dataSourceFilter = None

        if 'DETAIL ' in arg.upper():
            showDetail = True
            arg = arg.upper().replace('DETAIL ','')
        else: 
            showDetail = False

        if 'FEATURES ' in arg.upper():
            showFeatures = True
            arg = arg.upper().replace('FEATURES ','')
        else: 
            showFeatures = False

        if len(arg.split()) == 2 and arg.split()[0].upper() == 'SEARCH':
            lastToken = arg.split()[1]
            if not lastToken.isdigit() or lastToken == '0' or int(lastToken) > len(self.lastSearchResult):
                printWithNewLines('Select a valid index from the prior search results to use this command', 'B')
                return -1 if calledDirect else 0
            else:
                arg = str(self.lastSearchResult[int(lastToken)-1])

        getFlagList = []
        if apiVersion['VERSION'][0:1] > '1':
            getFlagList.append('G2_ENTITY_INCLUDE_ENTITY_NAME')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_DATA')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_MATCHING_INFO')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_FORMATTED_DATA')
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
            getFlagList.append('G2_ENTITY_INCLUDE_RELATED_ENTITY_NAME')
            getFlagList.append('G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO')
            getFlagList.append('G2_ENTITY_INCLUDE_RELATED_RECORD_SUMMARY')
        else:
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
        getFlagBits = self.computeApiFlags(getFlagList)

        if len(arg.split()) == 1:
            apiCall = f'getEntityByEntityIDV2({arg}, {getFlagBits}, response)' 
            try: 
                response = bytearray()
                retcode = g2Engine.getEntityByEntityIDV2(int(arg), getFlagBits, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print('\n' + str(err) + '\n')
                return -1 if calledDirect else 0

        elif len(arg.split()) == 2:
            apiCall = f'getEntityByRecordIDV2("{arg.split()[0]}", "{arg.split()[1]}", {getFlagBits}, response)'
            try: 
                response = bytearray()
                retcode = g2Engine.getEntityByRecordIDV2(arg.split()[0], arg.split()[1], getFlagBits, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print('\n' + str(err) + '\n')
                return -1 if calledDirect else 0
        else:
            argError(arg, 'incorrect number of parameters')
            return 0

        if debugOutput:
            showApiDebug('get', apiCall, getFlagList, json.loads(response) if response else '{}')

        if len(response) == 0:
            printWithNewLines('0 records found %s' % response, 'B')
            return -1 if calledDirect else 0

        resolvedJson = json.loads(str(response))
        relatedEntityCount = len(resolvedJson['RELATED_ENTITIES']) if 'RELATED_ENTITIES' in resolvedJson else 0
        entityID = str(resolvedJson['RESOLVED_ENTITY']['ENTITY_ID'])
        entityName = resolvedJson['RESOLVED_ENTITY']['ENTITY_NAME']
        #coloredEntityID = colorize(entityID, self.colors['entityid'])

        if showFeatures:
            tblColumns = []
            tblColumns.append({'name': 'Feature', 'width': 50, 'align': 'left'})
            tblColumns.append({'name': 'Description', 'width': 100, 'align': 'left'})
            tblColumns.append({'name': 'Elements', 'width': 100, 'align': 'left'})
            reportType = 'features'
            tblTitle = colorize(f'Entity {reportType} for: {entityID} - {entityName}', self.colors['entityid'])
            tblRows = self.getFeatures(entityID)
            self.renderTable(tblTitle, tblColumns, tblRows, titleColor=self.colors['entityTitle'])
            return 0
        else:
            tblColumns = []
            tblColumns.append({'name': 'Record ID', 'width': 50, 'align': 'left'})
            tblColumns.append({'name': 'Entity Data', 'width': 100, 'align': 'left'})
            tblColumns.append({'name': 'Additional Data', 'width': 100, 'align': 'left'})
            reportType = 'detail' if showDetail else 'summary'
            tblTitle = colorize(f'Entity {reportType} for: {entityID} - {entityName}', self.colors['entityid'])

            #--summarize by data source
            additionalDataSources = False
            if reportType == 'summary':
                dataSources = {}
                recordList = []
                for record in resolvedJson['RESOLVED_ENTITY']['RECORDS']:
                    if record['DATA_SOURCE'] not in dataSources:
                        dataSources[record['DATA_SOURCE']] = []
                    if dataSourceFilter and record['DATA_SOURCE'] not in dataSourceFilter:
                        additionalDataSources = True
                        continue
                    dataSources[record['DATA_SOURCE']].append(record)

                #--summarize by data source
                for dataSource in sorted(dataSources):
                    if dataSources[dataSource]:
                        recordData, entityData, otherData = self.formatRecords(dataSources[dataSource], reportType)
                        row = [recordData, entityData, otherData]
                    else:
                        row = [dataSource, ' ** suppressed ** ', '']
                    recordList.append(row)

            #--display each record
            else:
                recordList = []
                for record in sorted(resolvedJson['RESOLVED_ENTITY']['RECORDS'], key = lambda k: (k['DATA_SOURCE'], k['RECORD_ID'])):
                    if dataSourceFilter and record['DATA_SOURCE'] not in dataSourceFilter:
                        additionalDataSources = True
                        continue
                    recordData, entityData, otherData = self.formatRecords(record, 'entityDetail')
                    row = [recordData, entityData, otherData]
                    recordList.append(row)

            #if additionalDataSources:
            #    tblTitle += ' ' + colorize('** additionalDataSources **', 'blink'q)

            #--display if no relationships
            if relatedEntityCount == 0 or self.current_settings['show_relations_on_get'] == 'off':
                self.renderTable(tblTitle, tblColumns, recordList, titleColor=self.colors['entityTitle'])
                return 0

            #--otherwise begin the report and add the relationships
            self.renderTable(tblTitle, tblColumns, recordList, titleColor=self.colors['entityTitle'], displayFlag='begin')

            relationships = []
            for relatedEntity in resolvedJson['RELATED_ENTITIES']:
                relationship = {}
                relationship['MATCH_LEVEL'] = relatedEntity['MATCH_LEVEL']
                relationship['MATCH_KEY'] = relatedEntity['MATCH_KEY']
                relationship['ERRULE_CODE'] = relatedEntity['ERRULE_CODE']
                relationship['ENTITY_ID'] = relatedEntity['ENTITY_ID']
                relationship['ENTITY_NAME'] = relatedEntity['ENTITY_NAME']
                relationship['DATA_SOURCES'] = []
                for dataSource in relatedEntity['RECORD_SUMMARY']:
                    relationship['DATA_SOURCES'].append('%s (%s)' %(colorize(dataSource['DATA_SOURCE'], self.colors['datasource']), dataSource['RECORD_COUNT']))
                relationships.append(relationship)

            #tblTitle = f'{relatedEntityCount} related entities'
            tblTitle = colorize(f'Entities related to: {entityID} - {entityName}', self.colors['entityid'])
            tblColumns = []
            tblColumns.append({'name': 'Entity ID', 'width': 15, 'align': 'left'})
            tblColumns.append({'name': 'Entity Name', 'width': 75, 'align': 'left'})
            tblColumns.append({'name': 'Data Sources', 'width': 75, 'align': 'left'})
            tblColumns.append({'name': 'Match Level', 'width': 25, 'align': 'left'})
            tblColumns.append({'name': 'Match Key', 'width': 50, 'align': 'left'})
            relatedRecordList = []
            for relationship in sorted(relationships, key = lambda k: k['MATCH_LEVEL']):
                row = []
                row.append(colorize(str(relationship['ENTITY_ID']), self.colors['entityid']))
                row.append(relationship['ENTITY_NAME'])
                row.append('\n'.join(sorted(relationship['DATA_SOURCES'])))
                row.append(self.relatedMatchLevels[relationship['MATCH_LEVEL']])
                matchData = {}
                matchData['matchKey'] = relationship['MATCH_KEY']
                matchData['ruleCode'] = self.getRuleDesc(relationship['ERRULE_CODE'])
                row.append(formatMatchData(matchData, self.colors))
                relatedRecordList.append(row)
                    
            self.renderTable(tblTitle, tblColumns, relatedRecordList, titleColor=self.colors['entityTitle'], titleJustify='l', displayFlag='end')

        return 0

    # -----------------------------
    def formatRecords(self, recordList, reportType):
        dataSource = 'unknown'
        recordIdList = []
        primaryNameList = []
        otherNameList = []
        attributeList = []
        identifierList = []
        addressList = []
        phoneList = []
        otherList = []
        for record in [recordList] if type(recordList) != list else recordList:
 
            #--should only ever be one data source in the list
            dataSource = colorize(record['DATA_SOURCE'], self.colors['datasource']) 

            recordIdData = record['RECORD_ID']
            if reportType == 'detail':
                if record['MATCH_KEY']:
                    matchData = {}
                    matchData['matchKey'] = record['MATCH_KEY']
                    matchData['ruleCode'] = self.getRuleDesc(record['ERRULE_CODE'])
                    recordIdData += '\n' + formatMatchData(matchData, self.colors)
                if record['ERRULE_CODE']:
                    recordIdData += '\n  ' + colorize(self.getRuleDesc(record['ERRULE_CODE']), 'dim')
            recordIdList.append(recordIdData)

            for item in record['NAME_DATA']:
                if item.upper().startswith('PRIMARY'):
                    primaryNameList.append(colorizeAttribute(item, self.colors['highlight1']))
                else:
                    otherNameList.append(colorizeAttribute('NAME: ' + item if ':' not in item else item, self.colors['highlight1']))
            for item in record['ADDRESS_DATA']:
                addressList.append(colorizeAttribute('ADDRESS: ' + item if ':' not in item else item, self.colors['highlight1']))
            for item in record['PHONE_DATA']:
                phoneList.append(colorizeAttribute('PHONE: ' + item if ':' not in item else item, self.colors['highlight1']))
            for item in record['ATTRIBUTE_DATA']:
                attributeList.append(colorizeAttribute(item, self.colors['highlight1']))
            for item in record['IDENTIFIER_DATA']:
                identifierList.append(colorizeAttribute(item, self.colors['highlight1']))
            for item in sorted(record['OTHER_DATA']):
                if not self.isInternalAttribute(item) or reportType == 'detail':
                    otherList.append(colorizeAttribute(item, self.colors['highlight1']))

        recordDataList = [dataSource] + sorted(recordIdList)
        entityDataList = list(set(primaryNameList)) + list(set(otherNameList)) + sorted(set(attributeList)) + sorted(set(identifierList)) + list(set(addressList)) + list(set(phoneList))
        otherDataList = sorted(set(otherList))

        if reportType == 'detail':
            columnHeightLimit = 1000
        else:
            columnHeightLimit = 20

        recordData = '\n'.join(recordDataList[:columnHeightLimit])
        if len(recordDataList) > columnHeightLimit:
             recordData += '\n+%s more ' % str(len(recordDataList) - columnHeightLimit)

        entityData = '\n'.join(entityDataList[:columnHeightLimit])
        if len(entityDataList) > columnHeightLimit:
             entityData += '\n+%s more ' % str(len(entityDataList) - columnHeightLimit)

        otherData = '\n'.join(otherDataList[:columnHeightLimit])
        if len(otherDataList) > columnHeightLimit:
             otherData += '\n+%s more ' % str(len(otherDataList) - columnHeightLimit)

        return recordData, entityData, otherData

    # -----------------------------
    def getFeatures(self, entityID):

        getFlagList = []
        getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
        getFlagBits = self.computeApiFlags(getFlagList)

        apiCall = f'getEntityByEntityIDV2({entityID}, {getFlagBits}, response)' 
        try: 
            response = bytearray()
            retcode = g2Engine.getEntityByEntityIDV2(int(entityID), getFlagBits, response)
            response = response.decode() if response else ''
        except G2Exception as err:
            printWithNewLines(str(err), 'B')
            return -1 if calledDirect else 0

        if debugOutput:
            showApiDebug('get', apiCall, getFlagList, json.loads(response) if response else '{}')

        if len(response) == 0:
            printWithNewLines('0 records found %s' % response, 'B')
            return -1 if calledDirect else 0
        jsonData = json.loads(response)

        g2_diagnostic_module = G2Diagnostic()
        if apiVersion['VERSION'][0:1] == '2':
            g2_diagnostic_module.initV2('pyG2Diagnostic', iniParams, False)
        else: #--eventually deprecate the above
            g2_diagnostic_module.init('pyG2Diagnostic', iniParams, False)

        #--get the features in order
        orderedFeatureList = []
        for ftypeId in self.featureSequence: #sorted(featureArray, key=lambda k: self.featureSequence[k]):
            ftypeCode = self.ftypeLookup[ftypeId]['FTYPE_CODE']
            for distinctFeatureData in jsonData['RESOLVED_ENTITY']['FEATURES'].get(ftypeCode,[]):
                for featureData in distinctFeatureData['FEAT_DESC_VALUES']:
                    usageType = featureData.get('USAGE_TYPE')
                    orderedFeatureList.append({'ftypeCode': ftypeCode, 
                                               'usageType': distinctFeatureData.get('USAGE_TYPE'), 
                                               'featureDesc': featureData.get('FEAT_DESC'),
                                               'libFeatId': featureData['LIB_FEAT_ID']})
        tblRows = []
        for libFeatData in orderedFeatureList:
            ftypeCode = libFeatData['ftypeCode']
            usageType = libFeatData['usageType']
            libFeatId = libFeatData['libFeatId']
            featureDesc = libFeatData['featureDesc']

            try: 
                response = bytearray() 
                g2_diagnostic_module.getFeature(libFeatId, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print(err)
            jsonData = json.loads(response)

            ftypeDisplay = ftypeCode + (' (' + usageType + ')' if usageType else '')
            ftypeDisplay += '\n  ' + colorize(f'id: {libFeatId}', 'dim')

            #--standardize the order of the attributes
            for i in range(len(jsonData['ELEMENTS'])):
                attrRecord = self.ftypeAttrLookup[ftypeCode].get(jsonData['ELEMENTS'][i]['FELEM_CODE'])
                attrId = attrRecord['ATTR_ID'] if attrRecord else 9999999
                jsonData['ELEMENTS'][i]['ATTR_ID'] = attrId

            felemDisplayList = []
            for elementData in sorted(sorted(jsonData['ELEMENTS'], key=lambda k: (k['FELEM_CODE'])), key=lambda k: (k['ATTR_ID'])):
                felemDisplayList.append(colorize(elementData['FELEM_CODE'], self.colors['highlight1']) + ': ' +  elementData['FELEM_VALUE'])

            tblRows.append([ftypeDisplay, featureDesc, '\n'.join(felemDisplayList)])
        return tblRows

    # -----------------------------
    def getAmbiguousEntitySet(self, entityId):
        #--get other ambiguous relationships if this is the ambiguous entity
        getFlagList = []
        if apiVersion['VERSION'][0:1] > '1':
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
            getFlagList.append('G2_ENTITY_OPTION_INCLUDE_INTERNAL_FEATURES')
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
            getFlagList.append('G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO')
        else:
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
            getFlagList.append('G2_ENTITY_SHOW_FEATURES_EXPRESSED')
            getFlagList.append('G2_ENTITY_SHOW_FEATURES_STATS')
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
        getFlagBits = self.computeApiFlags(getFlagList)
        try: 
            response = bytearray()
            retcode = g2Engine.getEntityByEntityIDV2(int(entityId), getFlagBits, response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print(str(err))
            return None
        jsonData2 = json.loads(response)
        if debugOutput:
            apiCall = f'getEntityByEntityIDV2({entityId}, {getFlagBits}, response)'
            showApiDebug('getAmbiguousEntitySet', apiCall, getFlagList, jsonData2)

        ambiguousEntity = 'AMBIGUOUS_ENTITY' in jsonData2['RESOLVED_ENTITY']['FEATURES']
        if ambiguousEntity and 'RELATED_ENTITIES' in jsonData2:
            entitySet = []
            for relatedEntity in jsonData2['RELATED_ENTITIES']:
                if relatedEntity['IS_AMBIGUOUS'] != 0:
                    entitySet.append(str(relatedEntity['ENTITY_ID']))
            if len(entitySet) > 1:
                entitySet.append(entityId)
                return entitySet
        return None

    # -----------------------------
    def do_compare(self, arg, **kwargs):
        '\nCompares a set of entities by placing them side by side in a columnar format.'\
        '\n\nSyntax:' \
        '\n\tcompare <entity_id1> <entity_id2>' \
        '\n\tcompare search ' \
        '\n\tcompare search <top (n)>'
        if not argCheck('do_compare', arg, self.do_compare.__doc__):
            return

        showDetail = False #--old flag, replaced by why service which shows interal features

        #--no return code if called direct
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'

        #--get possible data source list
        if 'dataSourceFilter' in kwargs and self.current_settings['data_source_suppression'] == 'on':
            dataSourceFilter = kwargs['dataSourceFilter']
        else:
            dataSourceFilter = None

        fileName = None
        if type(arg) == str and 'TO' in arg.upper():
            fileName = arg[arg.upper().find('TO') + 2:].strip()
            fileName = arg[:arg.upper().find('TO')].strip()

        if type(arg) == str and 'SEARCH' in arg.upper():
            lastToken = arg.split()[len(arg.split())-1]
            if lastToken.isdigit():
                entityList = self.lastSearchResult[:int(lastToken)]
            else:
                entityList = self.lastSearchResult
        else:
            try: 
                if ',' in arg:
                    entityList = list(map(int, arg.split(',')))
                else:
                    entityList = list(map(int, arg.split()))
            except:
                printWithNewLines('error parsing argument [%s] into entity id numbers' % arg, 'S') 
                printWithNewLines('  expected comma or space delimited integers', 'E') 
                return -1 if calledDirect else 0

        if len(entityList) == 0:
            printWithNewLines('%s contains no valid entities' % arg, 'B') 
            return -1 if calledDirect else 0

        getFlagList = []
        if apiVersion['VERSION'][0:1] > '1':
            getFlagList.append('G2_ENTITY_INCLUDE_ENTITY_NAME')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_DATA')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_MATCHING_INFO')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_FORMATTED_DATA')
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
            getFlagList.append('G2_ENTITY_INCLUDE_RELATED_ENTITY_NAME')
            getFlagList.append('G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO')
            getFlagList.append('G2_ENTITY_INCLUDE_RELATED_RECORD_SUMMARY')
        else:
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
        getFlagBits = self.computeApiFlags(getFlagList)

        compareList = []
        for entityId in entityList:
            try:
                response = bytearray()
                retcode = g2Engine.getEntityByEntityIDV2(int(entityId), getFlagBits, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print('\n' + str(err) + '\n')
                return -1 if calledDirect else 0
            else:
                if len(response) == 0:
                    printWithNewLines('0 records found for %s' % entityId, 'B')
                    return -1 if calledDirect else 0

            jsonData = json.loads(response)
            if debugOutput:
                apiCall = f'getEntityByEntityIDV2({entityId}, {getFlagBits}, response)'
                showApiDebug('compare', apiCall, getFlagList, jsonData)

            entityData = {}
            entityData['entityID'] = jsonData['RESOLVED_ENTITY']['ENTITY_ID']
            entityData['dataSources'] = {}
            entityData['nameData'] = []
            entityData['attributeData'] = []
            entityData['identifierData'] = []
            entityData['addressData'] = []
            entityData['phoneData'] = []
            entityData['relationshipData'] = []
            entityData['otherData'] = []
            entityData['crossRelations'] = []
            entityData['otherRelations'] = []
 
            additionalDataSources = False
            for record in jsonData['RESOLVED_ENTITY']['RECORDS']:

                if record['DATA_SOURCE'] not in entityData['dataSources']:
                    if dataSourceFilter and record['DATA_SOURCE'] not in dataSourceFilter:
                        entityData['dataSources'][record['DATA_SOURCE']] = ['** suppressed **']
                    else:
                        entityData['dataSources'][record['DATA_SOURCE']] = [record['RECORD_ID']]
                else:
                    if dataSourceFilter and record['DATA_SOURCE'] in dataSourceFilter:
                        entityData['dataSources'][record['DATA_SOURCE']].append(record['RECORD_ID'])

                if dataSourceFilter and record['DATA_SOURCE'] not in dataSourceFilter:
                    additionalDataSources = True
                    continue

                if 'NAME_DATA' in record:
                    for item in record['NAME_DATA']:
                        if item not in entityData['nameData']:
                            entityData['nameData'].append(item)
                if 'ATTRIBUTE_DATA' in record:
                    for item in record['ATTRIBUTE_DATA']:
                        if item not in entityData['attributeData']:
                            entityData['attributeData'].append(item)
                if 'IDENTIFIER_DATA' in record:
                    for item in record['IDENTIFIER_DATA']:
                        if item not in entityData['identifierData']:
                            entityData['identifierData'].append(item)
                if 'ADDRESS_DATA' in record:
                    for item in record['ADDRESS_DATA']:
                        if item not in entityData['addressData']:
                            entityData['addressData'].append(item)
                if 'PHONE_DATA' in record:
                    for item in record['PHONE_DATA']:
                        if item not in entityData['phoneData']:
                            entityData['phoneData'].append(item)
                if 'RELATIONSHIP_DATA' in record:
                    for item in record['RELATIONSHIP_DATA']:
                        if item not in entityData['relationshipData']:
                            entityData['relationshipData'].append(item)
                if 'OTHER_DATA' in record:
                    for item in record['OTHER_DATA']:
                        if (showDetail or not self.isInternalAttribute(item)) and item not in entityData['otherData']:
                            entityData['otherData'].append(item)

            for relatedEntity in jsonData['RELATED_ENTITIES']:
                if relatedEntity['ENTITY_ID'] in entityList:
                    entityData['crossRelations'].append(relatedEntity) #'%s\n %s\n to %s' % (relatedEntity['MATCH_KEY'][1:], relatedEntity['ERRULE_CODE'], relatedEntity['ENTITY_ID']))
                else:
                    entityData['otherRelations'].append(relatedEntity) #{"MATCH_LEVEL": self.relatedMatchLevels[relatedEntity['MATCH_LEVEL']], "MATCH_KEY": relatedEntity['MATCH_KEY'][1:], "ERRULE_CODE": relatedEntity['ERRULE_CODE'], "ENTITY_ID": relatedEntity['ENTITY_ID'], "ENTITY_NAME": relatedEntity['ENTITY_NAME']})

            #--let them know these entities are not related to each other
            #if len(entityData['crossRelations']) == 0:
            #    entityData['crossRelations'].append('none')

            compareList.append(entityData)

        #--determine if there are any relationships in common
        for entityData1 in compareList:
            entityData1['relsInCommon'] = []
            for entityData2 in compareList:
                if entityData2['entityID'] == entityData1['entityID']:
                    continue
                for relation1 in entityData1['otherRelations']:
                    for relation2 in entityData2['otherRelations']:
                        commonRelation = False
                        if relation1['ENTITY_ID'] == relation2['ENTITY_ID']:
                            commonRelation = True
                        elif False:  #--ability to see if they are bothe related to a billy or a mary (by name) is turned off so ambiguous is more clear
                            if hasFuzzy:
                                commonRelation = fuzz.token_set_ratio(relation1['ENTITY_NAME'], relation2['ENTITY_NAME']) >= 90
                            else:
                                commonRelation = relation1['ENTITY_NAME'] == relation2['ENTITY_NAME']

                        if commonRelation and relation1 not in entityData1['relsInCommon']:
                            entityData1['relsInCommon'].append(relation1)

        #--create the column data arrays
        dataSourcesRow = []
        nameDataRow = []
        attributeDataRow = []
        identifierDataRow = []
        addressDataRow = []
        phoneDataRow = []
        relationshipDataRow = []
        otherDataRow = []
        crossRelsRow = []
        commonRelsRow = []

        for entityData in compareList:
            dataSourcesList = []
            for dataSource in sorted(entityData['dataSources']):
                for recordID in sorted(entityData['dataSources'][dataSource])[:5]:
                    dataSourcesList.append(colorizeAttribute(dataSource + ': ' + recordID, self.colors['datasource']))
                if len(entityData['dataSources'][dataSource]) > 5:
                    dataSourcesList.append(dataSource + ': +%s more ' % str(len(entityData['dataSources'][dataSource]) - 5))
            dataSourcesRow.append('\n'.join(dataSourcesList))

            nameDataRow.append('\n'.join([colorizeAttribute(x, self.colors['highlight1']) for x in sorted(entityData['nameData'])]))
            attributeDataRow.append('\n'.join([colorizeAttribute(x, self.colors['highlight1']) for x in sorted(entityData['attributeData'])]))
            identifierDataRow.append('\n'.join([colorizeAttribute(x, self.colors['highlight1']) for x in sorted(entityData['identifierData'])]))
            addressDataRow.append('\n'.join([colorizeAttribute(x, self.colors['highlight1']) for x in sorted(entityData['addressData'])]))
            phoneDataRow.append('\n'.join([colorizeAttribute(x, self.colors['highlight1']) for x in sorted(entityData['phoneData'])]))
            relationshipDataRow.append('\n'.join([colorizeAttribute(x, self.colors['highlight1']) for x in sorted(entityData['relationshipData'])]))
            otherDataRow.append('\n'.join([colorizeAttribute(x, self.colors['highlight1']) for x in sorted(entityData['otherData'])]))

            crossRelsList = []
            for relation in sorted(entityData['crossRelations'], key=lambda x: x['ENTITY_ID']):
                matchData = {}
                matchData['matchKey'] = relation['MATCH_KEY']
                matchData['ruleCode'] = self.getRuleDesc(relation['ERRULE_CODE'])
                if len(compareList) > 2:
                    matchData['entityId'] = relation['ENTITY_ID']
                crossRelsList.append(formatMatchData(matchData, self.colors))
            crossRelsRow.append('\n'.join(crossRelsList))

            commonRelsList = []
            for relation in sorted(entityData['relsInCommon'], key=lambda x: x['ENTITY_ID']):
                matchData = {}
                matchData['matchKey'] = relation['MATCH_KEY']
                matchData['ruleCode'] = self.getRuleDesc(relation['ERRULE_CODE'])
                matchData['entityId'] = relation['ENTITY_ID']
                commonRelsList.append(formatMatchData(matchData))
            commonRelsRow.append('\n'.join(commonRelsList))

        #--initialize table
        columnWidth = 75
        if False: #--disable adjustment in favor of less last table
            if len(entityList) <= 1:
                columnWidth = 100
            elif len(entityList) <= 3:
                columnWidth = 75
            elif len(entityList) <= 4:
                columnWidth = 50
            else:
                columnWidth = 25

        tblTitle = 'Comparison of Listed Entities'
        tblColumns = []
        tblColumns.append({'name': 'Entity ID', 'width': 16, 'align': 'left'})
        for entityId in entityList:
            tblColumns.append({'name': str(entityId), 'width': columnWidth, 'align': 'left'})

        #--set the row titles
        rowTitles = {}
        rowTitles['dataSourceRow'] = 'Sources'
        rowTitles['nameDataRow'] = 'Names'
        rowTitles['attributeDataRow'] = 'Attributes'
        rowTitles['identifierDataRow'] = 'Identifiers'
        rowTitles['addressDataRow'] = 'Addresses'
        rowTitles['phoneDataRow'] = 'Phones'
        rowTitles['otherDataRow'] = 'Other'
        rowTitles['crossRelsRow'] = 'Cross relations'
        rowTitles['commonRelsRow'] = 'Common relations'
        for rowTitle in rowTitles:
            rowTitles[rowTitle] = colorize(rowTitles[rowTitle], self.colors['rowtitle'])

        #--add the data
        tblRows = []
        tblRows.append([rowTitles['dataSourceRow']] + dataSourcesRow)
        if len(''.join(nameDataRow)) > 0:
            tblRows.append([rowTitles['nameDataRow']] + nameDataRow)
        if len(''.join(attributeDataRow)) > 0:
            tblRows.append([rowTitles['attributeDataRow']] + attributeDataRow)
        if len(''.join(identifierDataRow)) > 0:
            tblRows.append([rowTitles['identifierDataRow']] + identifierDataRow)
        if len(''.join(addressDataRow)) > 0:
            tblRows.append([rowTitles['addressDataRow']] + addressDataRow)
        if len(''.join(phoneDataRow)) > 0:
            tblRows.append([rowTitles['phoneDataRow']] + phoneDataRow)
        if len(''.join(otherDataRow)) > 0:
            tblRows.append([rowTitles['otherDataRow']] + otherDataRow)
        #if len(''.join(relationshipDataRow)) > 0:
        #    tblRows.append(['Disclosed Rels'] + relationshipDataRow)
        if len(''.join(crossRelsRow)) > 0:
           tblRows.append([rowTitles['crossRelsRow']] + crossRelsRow)
        if len(''.join(commonRelsRow)) > 0:
            tblRows.append([rowTitles['commonRelsRow']] + commonRelsRow)
        
        self.renderTable(tblTitle, tblColumns, tblRows, headerColor=self.colors['entityColumns'])

        return 0

    # -----------------------------
    def do_tree(self, arg, **kwargs):
        '\nDisplays an entity tree from a particular entity\'s point of view' \
        '\n\nSyntax:' \
        '\n\ttree <entity_id> degree <n>'
        if not argCheck('do_tree', arg, self.do_tree.__doc__):
            return

        entityId = None
        buildOutDegree = 1
        max_children_display = 10
        argList = arg.split()
        if len(argList) in (1,3):
            if argList[0].isdigit():
                entityId = int(argList[0])
            if len(argList) == 3 and argList[1].upper() == 'DEGREE' and argList[2].isdigit():
                buildOutDegree = int(argList[2])
        if not entityId:
            print('\nInvalid syntax\n')
            return

        entityParameter = json.dumps({'ENTITIES': [{'ENTITY_ID': entityId}]})

        #--these are default thresholds
        maxDegree = 0  #--really only used for entity paths
        maxEntities = 10000 #--for safety

        getFlagList = []    
        getFlagList.append('G2_ENTITY_INCLUDE_ENTITY_NAME')
        getFlagList.append('G2_ENTITY_INCLUDE_RECORD_SUMMARY')
        getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
        getFlagList.append('G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO')
        getFlagBits = self.computeApiFlags(getFlagList)

        apiCall = f'findNetworkByEntityIDV2({entityParameter} {maxDegree} {buildOutDegree} {maxEntities} {getFlagBits})'
        try: 
            response = bytearray()
            retcode = g2Engine.findNetworkByEntityIDV2(entityParameter, maxDegree, buildOutDegree, maxEntities, getFlagBits, response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print(f'\n{err}\n')
            return
        if debugOutput:
            showApiDebug('get', apiCall, getFlagList, json.loads(response) if response else '{}')
        json_data = json.loads(response)

        nodes = {}
        missing_entities = []

        current_parent_list = [{'NEXT_RELATED_ENTITY_I': 0, 'RELATED_ENTITY_LIST': [entityId], 'PRIOR_ENTITY_LIST': [entityId]}]
        while current_parent_list:

            #--decrement degree if done with this list
            current_parent_data = current_parent_list[-1]
            if current_parent_data['NEXT_RELATED_ENTITY_I'] == len(current_parent_data['RELATED_ENTITY_LIST']):
                current_parent_list.pop()
                continue

            #--get next related entity
            entity_id = current_parent_data['RELATED_ENTITY_LIST'][current_parent_data['NEXT_RELATED_ENTITY_I']]
            current_parent_list[len(current_parent_list)-1]['NEXT_RELATED_ENTITY_I'] += 1
            
            #--bypass if already built
            #if entity_id in nodes:
            #    continue

            nodes[entity_id] = {}
            nodes[entity_id]['RELATED_ENTITY_LIST'] = []

            entity_data = self.getEntityFromEntities(json_data['ENTITIES'], entity_id)
            if not entity_data:
                missing_entities.append(entity_id)
                nodes[entity_id]['ENTITY_NAME'] = 'not found!'
                continue

            nodes[entity_id]['ENTITY_NAME'] = entity_data['RESOLVED_ENTITY']['ENTITY_NAME']
            nodes[entity_id]['RECORD_SUMMARY'] =  entity_data['RESOLVED_ENTITY']['RECORD_SUMMARY']
            nodes[entity_id]['RELATED_ENTITY_COUNT'] = 0
            nodes[entity_id]['DISCLOSED_RELATION_COUNT'] = 0
            nodes[entity_id]['DISCLOSED_RELATION_CATEGORIES'] = {}
            nodes[entity_id]['DERIVED_RELATION_COUNT'] = 0
            nodes[entity_id]['DERIVED_RELATION_CATEGORIES'] = {}

            #--categorize relationships
            for relationship in entity_data.get('RELATED_ENTITIES', []):
                related_id = relationship['ENTITY_ID']

                #--bypass nodes already rendered in this tree
                if related_id in current_parent_list[len(current_parent_list)-1]['PRIOR_ENTITY_LIST']:
                    continue

                nodes[entity_id]['RELATED_ENTITY_COUNT'] += 1
                nodes[entity_id]['RELATED_ENTITY_LIST'].append(related_id)

                disclosed_keys, derived_keys = self.categorizeMatchkey(relationship['MATCH_KEY'])

                if disclosed_keys:  #--choose disclosed over derived
                    nodes[entity_id]['DISCLOSED_RELATION_COUNT'] += 1
                    key = '+'.join(sorted(disclosed_keys))
                    if key not in nodes[entity_id]['DISCLOSED_RELATION_CATEGORIES']:
                        nodes[entity_id]['DISCLOSED_RELATION_CATEGORIES'][key] = []
                    nodes[entity_id]['DISCLOSED_RELATION_CATEGORIES'][key].append(related_id)

                elif derived_keys:
                    nodes[entity_id]['DERIVED_RELATION_COUNT'] += 1
                    key = '+'.join(sorted(derived_keys))
                    if key not in nodes[entity_id]['DERIVED_RELATION_CATEGORIES']:
                        nodes[entity_id]['DERIVED_RELATION_CATEGORIES'][key] = []
                    nodes[entity_id]['DERIVED_RELATION_CATEGORIES'][key].append(related_id)

            #--start a new parent if any children
            if nodes[entity_id]['RELATED_ENTITY_LIST']:

                #--gather all prior level nodes so don't render twice
                next_prior_entity_list = []
                for parent_data in current_parent_list:
                    next_prior_entity_list += parent_data['RELATED_ENTITY_LIST']

                current_parent_list.append({'NEXT_RELATED_ENTITY_I': 0, 
                                            'RELATED_ENTITY_LIST': nodes[entity_id]['RELATED_ENTITY_LIST'],
                                            'PRIOR_ENTITY_LIST': next_prior_entity_list})

        #print('----\n', json.dumps(nodes, indent=4), '\n----')

        #--create the tree view
        tree_node_list = {}

        root_node = Node(entityId)
        root_node.node_desc = self.entityNodeDesc(nodes, entityId)
        tree_node_list[entityId] = root_node

        current_degree_list = [{'node': root_node, 'entity_id': entityId, 'next_child': 0}]
        while current_degree_list:

            #--determine what relationships to build under a relationship class/category tree
            if current_degree_list[-1]['next_child'] == 0:
                #print('\t' * (len(current_degree_list) - 1), 'entity:', current_degree_list[-1]['entity_id'])
                entity_id = current_degree_list[-1]['entity_id']
                related_ids_to_build = []

                for relation_fields in [['DISCLOSED', 'DISCLOSED_RELATION_COUNT', 'DISCLOSED_RELATION_CATEGORIES'], 
                                        ['DERIVED', 'DERIVED_RELATION_COUNT', 'DERIVED_RELATION_CATEGORIES']]:

                    class_name = relation_fields[0]
                    count_key = relation_fields[1]
                    category_key = relation_fields[2]

                    if nodes[entity_id][count_key] > 0:
                        class_node = Node(f'{nodes[entity_id]}-{class_name}')
                        colorized_class_name = colorize(class_name, self.colors['highlight1'])
                        #class_node.node_desc = f'{colorized_class_name} ({nodes[entity_id][count_key]})'
                        class_node.node_desc = f'{class_name} ({nodes[entity_id][count_key]})'

                        category_color = self.colors['highlight1'] if class_name == 'DISCLOSED' else self.colors['good']

                        for category in sorted(nodes[entity_id][category_key].keys()):
                            category_node = Node(f'{nodes[entity_id]}-{category}')
                            #colorized_category = colorize('+', self.colors['highlight1'] + ',dim').join(colorize(item, self.colors['highlight1']) for item in category.split('+'))
                            colorized_category = colorize('+'.join(category.split('+')), category_color)
                            category_node.node_desc = f'{colorized_category} ({len(nodes[entity_id][category_key][category])})'
                            cnt = 0
                            for related_id in sorted(nodes[entity_id][category_key][category]):
                                entity_node = Node(related_id)
                                entity_node.node_desc = self.entityNodeDesc(nodes, related_id)
                                tree_node_list[related_id] = entity_node
                                category_node.add_child(entity_node)

                                related_ids_to_build.append(related_id)
                                cnt += 1
                                if cnt == max_children_display:
                                    if len(nodes[entity_id][category_key][category]) > cnt:
                                        additional_node = Node(f'{nodes[entity_id]}-{category}-additional')
                                        additional_node.node_desc = f'+{len(nodes[entity_id][category_key][category])-cnt} more!'
                                        category_node.add_child(additional_node)
                                    break

                            class_node.add_child(category_node)
                        current_degree_list[-1]['node'].add_child(class_node)
                current_degree_list[-1]['children'] = related_ids_to_build

            if current_degree_list[-1]['next_child'] >= len(current_degree_list[-1]['children']):
                current_degree_list.pop()
                continue

            related_id = current_degree_list[-1]['children'][current_degree_list[-1]['next_child']]
            current_degree_list[-1]['next_child'] += 1

            #print('\t' * len(current_degree_list), 'related:', related_id, current_degree_list[-1]['prior_level_nodes'])

            #--start a new list of children if any
            if len(current_degree_list) < buildOutDegree and nodes[related_id]['RELATED_ENTITY_COUNT'] > 0:
                current_degree_list.append({'node': tree_node_list[related_id], 'entity_id': related_id, 'next_child': 0})

        print()
        print(root_node.render_tree())
        print()

        return

    # -----------------------------
    def entityNodeDesc(self, nodes, nodeId):
        if nodeId not in nodes:
            return f'{nodeId} not found!'

        nodeDesc = colorize(nodeId, self.colors['entityid']) + ' '

        if 'RECORD_SUMMARY' in nodes[nodeId]:
            nodeDesc += (' | '.join(colorize(ds['DATA_SOURCE'], self.colors['datasource']) for ds in nodes[nodeId]['RECORD_SUMMARY']) + ' ')

        if 'ENTITY_NAME' in nodes[nodeId]:
            nodeDesc += (nodes[nodeId]['ENTITY_NAME'])
        else:
            nodeDesc += 'no name'

        return nodeDesc

    # -----------------------------
    def getEntityFromEntities(self, _entity_list, _entity_id):
        #print(json.dumps(_entity_list[0:100]))
        item_list = [item for item in _entity_list if item['RESOLVED_ENTITY']['ENTITY_ID'] == _entity_id]
        if item_list:
            return item_list[0]
        return None

    # -----------------------------
    def categorizeMatchkey(self, match_key):
        # match_key example:
        #  'SAYARI(FATHER,SPOUSE:SON,SPOUSE)+ADDRESS+PHONE-DOB'
        disclosed_keys = [] 
        derived_keys = []
        key_list = re.split('(\+|\-)', match_key)

        i = 1
        while i < len(key_list):
            # ignore the minuses
            if key_list[i] in ('+'): 
                i += 1
                this_key = key_list[i]
                # derived
                if '(' not in this_key: 
                    derived_keys.append(this_key)
                # disclosed
                else: 
                    both_side_roles = this_key[this_key.find('(')+1:this_key.find(')')].split(':')
                    # left side of colon is from this entity's point of view
                    # but if blank, must use right side as both sides not required
                    roles_to_use = both_side_roles[0] if both_side_roles[0] else both_side_roles[1]
                    disclosed_keys += roles_to_use.split(',') 
            i += 1

        return disclosed_keys, derived_keys

    # -----------------------------
    def do_why(self,arg):
        '\nShows all the internals values for the entities desired in order to explain why they did or did not resolve.' \
        '\n\nSyntax:' \
        '\n\twhy <entity_id1>               (shows why the records in the entity resolved together)' \
        '\n\twhy <entity_id1> <entity_id2>  (shows how the different entities are related and/or why they did not resolve)' \
        '\n\twhy <data_source1> <record_id1> <data_source2> <record_id2>' \
        '\n\t                               (compares two data source records, showing how the either could resolve or relate)' \
        '\n\nColor legend:' \
        '\n\tgreen indicates the values matched and contributed to the overall score' \
        '\n\tred indicates the values did not match and hurt the overall score' \
        '\n\tyellow indicates the values did not match but did not hurt the overall score' \
        '\n\tcyan indicates the values only helped get the record on the candidate list' \
        '\n\tdimmed values were ignored (see the bracket legend below)' \
        '\n\nBracket legend:' \
        '\n\t[99] indicates how many entities share this value' \
        '\n\t[~] indicates that this value was not used to find candidates as too many entities share it' \
        '\n\t[!] indicates that this value was not not even scored as way too many entities share it' \
        '\n\t[#] indicates that this value was suppressed in favor of a more complete value\n'
        if type(arg) != list and not argCheck('do_why', arg, self.do_why.__doc__):
            return 

        #--no return code if called direct
        calledFrom = sys._getframe().f_back.f_code.co_name
        calledDirect = calledFrom != 'onecmd'

        #--see if already a list ... it will be if it came from audit
        if type(arg) == list:
            entityList = arg
        else:

            #fileName = None
            #if 'TO' in arg.upper():
            #    fileName = arg[arg.upper().find('TO') + 2:].strip()
            #    fileName = arg[:arg.upper().find('TO')].strip()
            oldWhyNot = apiVersion['VERSION'][0:1] < '2'
            if arg.upper().endswith(' OLD'):
                oldWhyNot = True
                arg = arg[0:-4]

            if 'SEARCH' in arg.upper():
                lastToken = arg.split()[len(arg.split())-1]
                if lastToken.isdigit():
                    entityList = self.lastSearchResult[:int(lastToken)]
                else:
                    entityList = self.lastSearchResult
            else:
                try: 
                    if ',' in arg:
                        entityList = arg.split(',')
                    else:
                        entityList = arg.split()
                except:
                    printWithNewLines('error parsing argument [%s] into entity id numbers' % arg, 'S') 
                    printWithNewLines('  expected comma or space delimited integers', 'E') 
                    return -1 if calledDirect else 0

        if len(entityList) == 1:
            whyType = 'whyEntity'
            tblTitle = 'Why for entity ID %s' % entityList[0]
            firstRowTitle = 'INTERNAL_ID'
            entityData = self.whyEntity(entityList)

        elif len(entityList) == 2 and not oldWhyNot: #--whyEntities() only available in 2.0
            whyType = 'whyNot1'
            tblTitle = 'Why NOT for listed entities'
            firstRowTitle = 'ENTITY_ID'
            entityData = self.whyNot2(entityList)

        elif len(entityList) == 4 and entityList[0].upper() in self.dsrcCodeLookup:
            whyType = 'whyRecords'
            tblTitle = 'Why records - %s: %s vs %s: %s' % (entityList[0].upper(), entityList[1], entityList[2].upper(), entityList[3])
            firstRowTitle = 'INTERNAL_ID'
            entityData = self.whyRecords(entityList)

        else:
            whyType = 'whyNot2'
            tblTitle = 'Why NOT for listed entities'
            firstRowTitle = 'ENTITY_ID'
            entityData = self.whyNotMany(entityList)

        if not entityData:
            printWithNewLines('No records found!', 'B')
            return -1 if calledDirect else 0

        tblColumns = [{'name': colorize(firstRowTitle, self.colors['rowtitle']), 'width': 50, 'align': 'left'}]
        tblRows = []

        dataSourceRow = ['DATA_SOURCES']
        matchKeyRow = ['WHY_RESULT']
        crossRelationsRow = ['RELATIONSHIPS']
        featureArray = {}
        for entityId in sorted(entityData.keys()):

            #--add the column
            color = self.colors['entityid'] if firstRowTitle == 'ENTITY_ID' else 'dim'
            tblColumns.append({'name': colorize(entityId, color) , 'width': 75, 'align': 'left'})

            #--add the data sources
            dataSourceRow.append('\n'.join(sorted(entityData[entityId]['dataSources'])))

            #--add the cross relationships
            if 'crossRelations' in entityData[entityId]:
                relationList = []
                for relationship in [x for x in sorted(entityData[entityId]['crossRelations'], key=lambda k: k['entityId'])]:
                    if len(entityList) <= 2: #--supress to entity if only 2
                        del relationship['entityId']
                    relationList.append(formatMatchData(relationship))
                crossRelationsRow.append('\n'.join(relationList))

            #--add the matchKey
            if 'whyKey' not in entityData[entityId] or not entityData[entityId]['whyKey']:
                matchKeyRow.append(colorize('Not found!', self.colors['bad']))
            elif type(entityData[entityId]['whyKey']) != list:
                matchKeyRow.append(formatMatchData(entityData[entityId]['whyKey'], self.colors))
            else:
                tempList = []
                for whyKey in [x for x in sorted(entityData[entityId]['whyKey'], key=lambda k: k['entityId'])]:
                    if 'entityId' in whyKey and len(entityList) <= 2:  #--supress to entity if only 2
                        del whyKey['entityId']
                    tempList.append(formatMatchData(whyKey, self.colors))
                matchKeyRow.append('\n'.join(tempList))

            #--prepare the feature rows
            whyKey = entityData[entityId]['whyKey']
            for libFeatId in entityData[entityId]['features']:
                featureData = entityData[entityId]['features'][libFeatId]
                ftypeId = featureData['ftypeId']
                formattedFeature = self.whyFormatFeature(featureData, whyKey)
                if ftypeId not in featureArray:
                    featureArray[ftypeId] = {}
                if entityId not in featureArray[ftypeId]:
                    featureArray[ftypeId][entityId] = []
                featureArray[ftypeId][entityId].append(formattedFeature)

        #--prepare the table
        tblRows.append(dataSourceRow)
        if len(crossRelationsRow) > 1:
            tblRows.append(crossRelationsRow)
        tblRows.append(matchKeyRow)

        #--add the feature rows
        for ftypeId in sorted(featureArray, key=lambda k: self.featureSequence[k]):
            featureRow = [self.ftypeLookup[ftypeId]['FTYPE_CODE'] if ftypeId in self.ftypeLookup else 'unknown']
            for entityId in sorted(entityData.keys()):
                if entityId not in featureArray[ftypeId]:
                    featureRow.append('')
                else:
                    featureList = []
                    for featureDict in sorted(sorted(featureArray[ftypeId][entityId], key=lambda k: (k['featDesc'])), key=lambda k: (k['sortOrder'])):
                        featureList.append(featureDict['formattedFeatDesc'])
                    featureRow.append('\n'.join(featureList))
            tblRows.append(featureRow)


        #--colorize the first column
        for i in range(len(tblRows)):
            tblRows[i][0] = colorize(tblRows[i][0], self.colors['rowtitle'])

        #--display the table
        self.renderTable(tblTitle, tblColumns, tblRows, titleColor = self.colors['entityTitle'])

        return 0

    # -----------------------------
    def whyEntity(self, entityList):
        whyFlagList = ['G2_WHY_ENTITY_DEFAULT_FLAGS']
        whyFlagBits = self.computeApiFlags(whyFlagList)
        try:
            response = bytearray()
            retcode = g2Engine.whyEntityByEntityIDV2(int(entityList[0]), whyFlagBits, response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print('\n' + str(err) + '\n')
            return None
        if len(response) == 0:
            return None
        jsonData = json.loads(response)
        if debugOutput:
            apiCall = f'whyEntityByEntityIDV2({entityList[0]}, {whyFlagBits}, response)'
            showApiDebug('whyEntity', apiCall, whyFlagList, jsonData)

        entityData = {}
        for whyResult in jsonData['WHY_RESULTS']:
            internalId = whyResult['INTERNAL_ID']
            entityId = whyResult['ENTITY_ID']
            thisId = internalId #--will eventually be entityId when why not function is added
            entityData[thisId] = {}

            records = self.whyFmtRecordList(whyResult['FOCUS_RECORDS'])
            features = self.whyGetFeatures(jsonData, entityId, internalId)
            if 'MATCH_INFO' not in whyResult:
                whyKey = None
            else: 
                whyKey, features = self.whyAddMatchInfo(features, whyResult['MATCH_INFO'])

            entityData[thisId]['dataSources'] = records
            entityData[thisId]['whyKey'] = whyKey
            entityData[thisId]['features'] = features

        return entityData

    # -----------------------------
    def whyRecords(self, entityList):
        whyFlagList = ['G2_WHY_ENTITY_DEFAULT_FLAGS']
        whyFlagBits = self.computeApiFlags(whyFlagList)
        try:
            response = bytearray()
            retcode = g2Engine.whyRecordsV2(entityList[0], entityList[1], entityList[2], entityList[3], whyFlagBits, response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print('\n' + str(err) + '\n')
            return None 
        if len(response) == 0:
            return None 
        jsonData = json.loads(response)
        if debugOutput:
            apiCall = f'whyRecordsV2("{entityList[0]}", "{entityList[1]}", "{entityList[2]}", "{entityList[3]}", {whyFlagBits}, response)'
            showApiDebug('whyEntity', apiCall, whyFlagList, jsonData)

        entityData = {}
        for whyResult in jsonData['WHY_RESULTS']:

            #--get the first record
            internalId = whyResult['INTERNAL_ID']
            entityId = whyResult['ENTITY_ID']
            thisId = internalId #--will eventually be entityId when why not function is added
            entityData[thisId] = {}

            records = self.whyFmtRecordList(whyResult['FOCUS_RECORDS'])
            features = self.whyGetFeatures(jsonData, entityId, internalId)
            if 'MATCH_INFO' not in whyResult:
                whyKey = None
            else: 
                whyKey, features = self.whyAddMatchInfo(features, whyResult['MATCH_INFO'])

            entityData[thisId]['dataSources'] = records
            entityData[thisId]['whyKey'] = whyKey
            entityData[thisId]['features'] = features

            #--get the second record
            internalId = whyResult['INTERNAL_ID_2']
            entityId = whyResult['ENTITY_ID_2']
            thisId = internalId #--will eventually be entityId when why not function is added
            entityData[thisId] = {}

            records = self.whyFmtRecordList(whyResult['FOCUS_RECORDS_2'])
            features = self.whyGetFeatures(jsonData, entityId, internalId)
            if 'MATCH_INFO' not in whyResult:
                whyKey = None
            else: 
                whyKey, features = self.whyAddMatchInfo(features, whyResult['MATCH_INFO'])

            entityData[thisId]['dataSources'] = records
            entityData[thisId]['whyKey'] = whyKey
            entityData[thisId]['features'] = features

            break #--there can only really be one, so lets be done!

        return entityData

    # -----------------------------
    def whyNot2(self, entityList):

        try: entityList = [int(x) for x in entityList]
        except: 
            printWithNewLines('Invalid parameters')
            return None

        whyFlagList = ['G2_WHY_ENTITY_DEFAULT_FLAGS']
        whyFlagBits = self.computeApiFlags(whyFlagList)
        try:
            response = bytearray()
            retcode = g2Engine.whyEntitiesV2(int(entityList[0]), int(entityList[1]), whyFlagBits, response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print('\n' + str(err) + '\n')
            return None 
        if len(response) == 0:
            return None 
        jsonData = json.loads(response)
        if debugOutput:
            apiCall = f'whyEntitiesV2({entityList[0]}, {entityList[1]}, {whyFlagBits}, response)'
            showApiDebug('basic whyNot (between 2 entities)', apiCall, whyFlagList, jsonData)

        entityData = {}
        for whyResult in jsonData['WHY_RESULTS']:

            for thisId in [whyResult['ENTITY_ID'], whyResult['ENTITY_ID_2']]:
                entityData[thisId] = {}
                bestEntity = None
                for resolvedEntity in jsonData['ENTITIES']:
                    if resolvedEntity['RESOLVED_ENTITY']['ENTITY_ID'] == thisId:
                        bestEntity = resolvedEntity
                        break
                if not bestEntity:
                    print('\nInternal error: resolved entity %s missing!\n' % thisId)
                    return None 

                records = self.whyFmtRecordList(bestEntity['RESOLVED_ENTITY']['RECORDS'])
                features = {}
                for ftypeCode in bestEntity['RESOLVED_ENTITY']['FEATURES']:
                    for distinctFeatureRecord in bestEntity['RESOLVED_ENTITY']['FEATURES'][ftypeCode]:
                        for featRecord in distinctFeatureRecord['FEAT_DESC_VALUES']:
                            libFeatId = featRecord['LIB_FEAT_ID']
                            if libFeatId not in features:
                                features[libFeatId] = {}
                                features[libFeatId]['ftypeId'] = self.ftypeCodeLookup[ftypeCode]['FTYPE_ID']
                                features[libFeatId]['ftypeCode'] = ftypeCode
                                features[libFeatId]['featDesc'] = featRecord['FEAT_DESC']
                                features[libFeatId]['isCandidate'] = featRecord['USED_FOR_CAND']
                                features[libFeatId]['isScored'] = featRecord['USED_FOR_SCORING']
                                features[libFeatId]['entityCount'] = featRecord['ENTITY_COUNT']
                                features[libFeatId]['candidateCapReached'] = featRecord['CANDIDATE_CAP_REACHED']
                                features[libFeatId]['scoringCapReached'] = featRecord['SCORING_CAP_REACHED']
                                features[libFeatId]['scoringWasSuppressed'] = featRecord['SUPPRESSED']

                if 'MATCH_INFO' not in whyResult:
                    whyKey = None
                else: 
                    whyKey, features = self.whyAddMatchInfo(features, whyResult['MATCH_INFO'])

                entityData[thisId]['dataSources'] = records
                entityData[thisId]['whyKey'] = whyKey
                entityData[thisId]['features'] = features

                entityData[thisId]['crossRelations'] = []
                for relatedEntity in bestEntity['RELATED_ENTITIES']:
                    if relatedEntity['ENTITY_ID'] in entityList:
                        relationship = {}
                        relationship['entityId'] = relatedEntity['ENTITY_ID']
                        relationship['matchKey'] = relatedEntity['MATCH_KEY']
                        relationship['ruleCode'] = self.getRuleDesc(relatedEntity['ERRULE_CODE'])
                        entityData[thisId]['crossRelations'].append(relationship)

        #if debugOutput:
        #    showDebug('whyEntity-reporting structure', entityData)

        return entityData

    # -----------------------------
    def whyNotMany(self, entityList):
        try: entityList = [int(x) for x in entityList]
        except: 
            printWithNewLines('Invalid parameters')
            return None

        whyFlagList = []

        if apiVersion['VERSION'][0:1] > '1':
            whyFlagList.append('G2_WHY_ENTITY_DEFAULT_FLAGS')
            whyFlagList.append('G2_ENTITY_INCLUDE_RECORD_JSON_DATA')
        else:
            whyFlagList.append('G2_WHY_ENTITY_DEFAULT_FLAGS')
        whyFlagBits = self.computeApiFlags(whyFlagList)

        masterFtypeList = []
        entityData = {}
        for entityId in entityList:
            entityData[entityId] = {}
            try:
                response = bytearray()
                retcode = g2Engine.whyEntityByEntityIDV2(int(entityId), whyFlagBits, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print('\n' + str(err) + '\n')
                return None
            jsonData = json.loads(response)
            if len(jsonData['ENTITIES']) == 0:
                printWithNewLines('No records found for %s' % entityId, 'B')
                return None
            if debugOutput:
                apiCall = f'whyEntityByEntityIDV2({entityId}, {whyFlagBits}, response)'
                showApiDebug('advanced whyNot - step 1 (get features and usage stats) ', apiCall, whyFlagList, jsonData)

            #--add the data sources and create search json
            searchJson = {}
            entityData[entityId]['dataSources'] = []
            for record in jsonData['ENTITIES'][0]['RESOLVED_ENTITY']['RECORDS']:
                entityData[entityId]['dataSources'].append('%s: %s' %(record['DATA_SOURCE'], record['RECORD_ID']))
                if not searchJson:
                    searchJson = record['JSON_DATA']
                else: #--merge the json records
                    rootAttributes = {}
                    for rootAttribute in record['JSON_DATA']:
                        if type(record['JSON_DATA'][rootAttribute]) != list:
                            rootAttributes[rootAttribute] = record['JSON_DATA'][rootAttribute]
                        else:
                            if rootAttribute not in searchJson:
                                searchJson[rootAttribute] = []
                            for subRecord in record['JSON_DATA'][rootAttribute]:
                                searchJson[rootAttribute].append(subRecord)
                    if rootAttributes:
                        if 'ROOT_ATTRIBUTES' not in searchJson:
                            searchJson['ROOT_ATTRIBUTES'] = []
                        searchJson['ROOT_ATTRIBUTES'].append(rootAttributes)

            #--get info for these features from the resolved entity section
            entityData[entityId]['features'] = {}
            for ftypeCode in jsonData['ENTITIES'][0]['RESOLVED_ENTITY']['FEATURES']:
                for featRecord in jsonData['ENTITIES'][0]['RESOLVED_ENTITY']['FEATURES'][ftypeCode]:
                    for featValues in featRecord['FEAT_DESC_VALUES']:
                        libFeatId = featValues['LIB_FEAT_ID']
                        if libFeatId not in entityData[entityId]['features']:
                            entityData[entityId]['features'][libFeatId] = {}
                            entityData[entityId]['features'][libFeatId]['ftypeId'] = self.ftypeCodeLookup[ftypeCode]['FTYPE_ID']
                            entityData[entityId]['features'][libFeatId]['ftypeCode'] = ftypeCode
                            entityData[entityId]['features'][libFeatId]['featDesc'] = featValues['FEAT_DESC']
                            entityData[entityId]['features'][libFeatId]['isCandidate'] = featValues['USED_FOR_CAND']
                            entityData[entityId]['features'][libFeatId]['isScored'] = featValues['USED_FOR_SCORING']
                            entityData[entityId]['features'][libFeatId]['entityCount'] = featValues['ENTITY_COUNT']
                            entityData[entityId]['features'][libFeatId]['candidateCapReached'] = featValues['CANDIDATE_CAP_REACHED']
                            entityData[entityId]['features'][libFeatId]['scoringCapReached'] = featValues['SCORING_CAP_REACHED']
                            entityData[entityId]['features'][libFeatId]['scoringWasSuppressed'] = featValues['SUPPRESSED']
                            if entityData[entityId]['features'][libFeatId]['ftypeId'] not in masterFtypeList:
                                masterFtypeList.append(entityData[entityId]['features'][libFeatId]['ftypeId'])

            #--see how this entity is related to the others
            getFlagList = []
            if apiVersion['VERSION'][0:1] > '1':
                getFlagList.append('G2_ENTITY_BRIEF_DEFAULT_FLAGS')
            else:
                getFlagList.append('G2_ENTITY_BRIEF_FORMAT')
            getFlagBits = self.computeApiFlags(getFlagList)
            try: 
                response = bytearray()
                retcode = g2Engine.getEntityByEntityIDV2(int(entityId), getFlagBits, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print(str(err))
                return
            jsonData2 = json.loads(response)
            if debugOutput:
                apiCall = f'getEntityByEntityIDV2({entityId}, {getFlagBits}, response)'
                showApiDebug('advanced whyNot - step 2 (get actual relationships)', apiCall, getFlagList, jsonData2)

            entityData[entityId]['crossRelations'] = []
            for relatedEntity in jsonData2['RELATED_ENTITIES']:
                if relatedEntity['ENTITY_ID'] in entityList:
                    relationship = {}
                    relationship['entityId'] = relatedEntity['ENTITY_ID']
                    relationship['matchKey'] = relatedEntity['MATCH_KEY']
                    relationship['ruleCode'] = self.getRuleDesc(relatedEntity['ERRULE_CODE'])
                    entityData[entityId]['crossRelations'].append(relationship)

            #--search for this entity to get the scores against the others
            searchFlagList = []
            if apiVersion['VERSION'][0:1] > '1':
                searchFlagList.append('G2_SEARCH_INCLUDE_ALL_ENTITIES')
                searchFlagList.append('G2_SEARCH_INCLUDE_FEATURE_SCORES')
                searchFlagList.append('G2_ENTITY_INCLUDE_ENTITY_NAME')
                searchFlagList.append('G2_ENTITY_INCLUDE_RECORD_DATA')
            else:
                searchFlagList.append('G2_ENTITY_INCLUDE_NO_FEATURES')
                searchFlagList.append('G2_ENTITY_INCLUDE_NO_RELATIONS')
            searchFlagBits = self.computeApiFlags(searchFlagList)

            try: 
                response = bytearray()
                retcode = g2Engine.searchByAttributesV2(json.dumps(searchJson), searchFlagBits, response)
                response = response.decode() if response else ''
            except G2Exception as err:
                print(json.dumps(searchJson, indent=4))
                print(str(err))
                return
            jsonData2 = json.loads(response)
            if debugOutput:
                showDebug('searchMessage', searchJson)
                apiCall = f'searchByAttributesV2(searchMessage, {searchFlagBits}, response)'
                showApiDebug('advanced whyNot - step 3 (search to see if it can find the others)', apiCall, searchFlagList, jsonData2)

            entityData[entityId]['whyKey'] = []
            for resolvedEntityBase in jsonData2['RESOLVED_ENTITIES']:
                 resolvedEntity = resolvedEntityBase['ENTITY']['RESOLVED_ENTITY']
                 resolvedEntityMatchInfo = resolvedEntityBase['MATCH_INFO']
                 if resolvedEntity['ENTITY_ID'] in entityList and resolvedEntity['ENTITY_ID'] != entityId:
                    whyKey = {}
                    whyKey['matchKey'] = resolvedEntityMatchInfo['MATCH_KEY'] 
                    whyKey['ruleCode'] = self.getRuleDesc(resolvedEntityMatchInfo['ERRULE_CODE'])
                    whyKey['entityId'] = resolvedEntity['ENTITY_ID']
                    entityData[entityId]['whyKey'].append(whyKey)
                    for featureCode in resolvedEntityMatchInfo['FEATURE_SCORES']:
                        #--get the best score for the feature
                        bestScoreRecord = None
                        for scoreRecord in resolvedEntityMatchInfo['FEATURE_SCORES'][featureCode]:
                            #print (json.dumps(scoreRecord, indent=4))
                            if not bestScoreRecord:
                                bestScoreRecord = scoreRecord
                            elif 'GNR_FN' in scoreRecord and scoreRecord['GNR_FN'] > bestScoreRecord['GNR_FN']:
                                bestScoreRecord = scoreRecord
                            elif 'BT_FN' in scoreRecord and scoreRecord['BT_FN'] > bestScoreRecord['BT_FN']:
                                bestScoreRecord = scoreRecord
                            elif 'FULL_SCORE' in scoreRecord and scoreRecord['FULL_SCORE'] > bestScoreRecord['FULL_SCORE']:
                                bestScoreRecord = scoreRecord
                        #--update the entity feature
                        for libFeatId in entityData[entityId]['features']:
                            #print ('-' * 50)
                            #print(entityData[entityId]['features'][libFeatId])
                            if entityData[entityId]['features'][libFeatId]['ftypeCode'] == featureCode and entityData[entityId]['features'][libFeatId]['featDesc'] in (bestScoreRecord['INBOUND_FEAT'], bestScoreRecord['CANDIDATE_FEAT']):
                                matchScore = 0
                                matchLevel = 'DIFF'
                                if 'GNR_FN' in bestScoreRecord:
                                    matchScore = bestScoreRecord['GNR_FN']
                                    if 'GNR_ON' in bestScoreRecord and bestScoreRecord['GNR_ON'] >= 0:
                                        matchScoreDisplay = 'org:%s' % bestScoreRecord['GNR_ON']
                                    else:
                                        matchScoreDisplay = 'score:%s' % bestScoreRecord['GNR_FN']
                                        if 'GNR_GN' in bestScoreRecord and bestScoreRecord['GNR_GN'] >= 0:
                                            matchScoreDisplay += '|giv:%s' % bestScoreRecord['GNR_GN']
                                        if 'GNR_SN' in bestScoreRecord and bestScoreRecord['GNR_SN'] >= 0:
                                            matchScoreDisplay += '|sur:%s' % bestScoreRecord['GNR_SN']
                                    if matchScore == 100:
                                        matchLevel = 'SAME'
                                    else:
                                        if 'NAME' in resolvedEntityMatchInfo['MATCH_KEY']:
                                            matchLevel = 'CLOSE'
                                elif 'BT_FN' in bestScoreRecord:
                                    matchScore = bestScoreRecord['BT_FN']
                                    if 'BT_ON' in bestScoreRecord and bestScoreRecord['BT_ON'] > 0:
                                        matchScoreDisplay = 'org:%s' % bestScoreRecord['BT_ON']
                                    else:
                                        matchScoreDisplay = 'full:%s' % bestScoreRecord['BT_FN']
                                    if matchScore == 100:
                                        matchLevel = 'SAME'
                                    else:
                                        if 'NAME' in resolvedEntityMatchInfo['MATCH_KEY']:
                                            matchLevel = 'CLOSE'
                                else:
                                    matchScore = bestScoreRecord['FULL_SCORE']
                                    matchScoreDisplay = str(bestScoreRecord['FULL_SCORE'])
                                    if matchScore == 100:
                                        matchLevel = 'SAME'
                                    else:
                                        cfrtnRecord = self.cfrtnLookup[self.cfuncLookup[self.scoredFtypeCodes[featureCode]['CFUNC_ID']]['CFUNC_ID']]
                                        if matchScore >= cfrtnRecord['CLOSE_SCORE']:
                                            matchLevel = 'CLOSE'
                                
                                if 'matchScore' not in entityData[entityId]['features'][libFeatId] or matchScore > entityData[entityId]['features'][libFeatId]['matchScore']:
                                    entityData[entityId]['features'][libFeatId]['wasScored'] = 'Yes'
                                    entityData[entityId]['features'][libFeatId]['matchedFeatId'] = 0
                                    entityData[entityId]['features'][libFeatId]['matchedFeatDesc'] = bestScoreRecord['CANDIDATE_FEAT'] if entityData[entityId]['features'][libFeatId]['featDesc'] == bestScoreRecord['INBOUND_FEAT'] else bestScoreRecord['INBOUND_FEAT']
                                    entityData[entityId]['features'][libFeatId]['matchScore'] = matchScore
                                    entityData[entityId]['features'][libFeatId]['matchScoreDisplay'] = matchScoreDisplay
                                    entityData[entityId]['features'][libFeatId]['matchLevel'] = matchLevel
                                break

        #--find matching features whether scored or not (accounts for candidate keys as well)
        for entityId in entityList:
            for libFeatId in entityData[entityId]['features']:
                for entityId1 in entityList:
                    if entityId != entityId1 and libFeatId in entityData[entityId1]['features']:
                        entityData[entityId]['features'][libFeatId]['wasCandidate'] = 'Yes' if entityData[entityId]['features'][libFeatId]['isCandidate'] == 'Y' else 'No'
                        entityData[entityId]['features'][libFeatId]['matchScore'] = 100
                        entityData[entityId]['features'][libFeatId]['matchLevel'] = 'SAME'
                        break

        return entityData

    # -----------------------------
    def whyFmtRecordList(self, recordList):
        recordsBysource = {}
        for record in recordList:
            if record['DATA_SOURCE'] not in recordsBysource:
                recordsBysource[record['DATA_SOURCE']] = []
            recordsBysource[record['DATA_SOURCE']].append(record['RECORD_ID'])
        recordDisplay = []
        for dataSource in sorted(recordsBysource.keys()):
            coloredDataSource = colorize(dataSource, self.colors['datasource'])
            if len(recordsBysource[dataSource]) > 1:
                recordDisplay.append(f'{coloredDataSource}: {len(recordsBysource[dataSource])} records')
            else:
                for recordId in sorted(recordsBysource[dataSource]):
                    recordDisplay.append(f'{coloredDataSource}: {recordId}')
        return recordDisplay

    # -----------------------------
    def feature_counter_display(self, featureData):
        counterDisplay = '['
        if featureData['candidateCapReached'] == 'Y':
            counterDisplay += '~'
        if featureData['scoringCapReached'] == 'Y':
            counterDisplay += '!'
        if featureData['scoringWasSuppressed'] == 'Y':
            counterDisplay += '#'
        counterDisplay += str(featureData['entityCount']) + ']'
        return counterDisplay

    # -----------------------------
    def whyFormatFeature(self, featureData, whyKey):
        featureData['formattedFeatDesc'] = featureData['featDesc'].strip()
        ftypeCode = featureData['ftypeCode']
        featureData['counterDisplay'] = self.feature_counter_display(featureData)
        featureData['formattedFeatDesc'] += ' ' + featureData['counterDisplay']
        featureData['formattedFeatDesc1'] = ''
        featureData['formattedFeatDesc2'] = ''

        dimmit = any(c in featureData['counterDisplay'] for c in ['~','!','#'])
        featureData['sortOrder'] = 3
        if 'wasScored' in featureData:
            if featureData['matchLevel'] in ('SAME', 'CLOSE'):
                featureData['sortOrder'] = 1
                featureData['featColor'] = self.colors['good'] 
            else:
                featureData['sortOrder'] = 2
                if not whyKey:
                    featureData['featColor'] = self.colors['bad']
                elif type(whyKey) == dict and ('-' + ftypeCode) not in whyKey['matchKey']:
                    featureData['featColor'] = self.colors['caution']
                elif type(whyKey) == list and ('-' + ftypeCode) not in whyKey[0]['matchKey']:
                    featureData['featColor'] = self.colors['caution']
                else:
                    featureData['featColor'] = self.colors['bad']
            #if dimmit: 
            #    featureData['featColor'] += ',dim'
            featureData['formattedFeatDesc'] = colorize(featureData['formattedFeatDesc'], featureData['featColor'])
            featureData['formattedFeatDesc1'] = featureData['formattedFeatDesc']

            #--note: addresses may score same tho not exact!
            if featureData['matchLevel'] != 'SAME' or featureData['matchedFeatDesc'] != featureData['featDesc']:  
                featureData['formattedFeatDesc'] += '\n  '
                featureData['formattedFeatDesc'] += colorize('%s (%s)' % (featureData['matchedFeatDesc'].strip(), featureData['matchScoreDisplay']), featureData['featColor'] + ',italics')
            featureData['formattedFeatDesc2'] = colorize('%s (%s)' % (featureData['matchedFeatDesc'].strip(), featureData['matchScoreDisplay']), featureData['featColor'])

        elif 'matchScore' in featureData: #--must be same and likley a candidate builder
            featureData['sortOrder'] = 1
            featureData['featColor'] = self.colors['highlight1'] + (',dim' if dimmit else '')
            featureData['formattedFeatDesc'] = colorize(featureData['formattedFeatDesc'], featureData['featColor'])
            featureData['formattedFeatDesc1'] = featureData['formattedFeatDesc']

        else:
            if ftypeCode == 'AMBIGUOUS_ENTITY' and featureData['formattedFeatDesc'] .startswith(' ['):
                featureData['formattedFeatDesc']  = 'Ambiguous!'
                featureData['formattedFeatDesc']  = colorize(featDesc, self.colors['bad'])
            featureData['formattedFeatDesc1'] = featureData['formattedFeatDesc']

        #--sort rejected matches lower 
        if dimmit: 
            featureData['sortOrder'] += .5

        return featureData

    # -----------------------------
    def whyGetFeatures(self, jsonData, entityId, internalId = None):
        bestEntity = None
        bestRecord = None
        for resolvedEntity in jsonData['ENTITIES']:
            if resolvedEntity['RESOLVED_ENTITY']['ENTITY_ID'] == entityId:
                for dsrcRecord in resolvedEntity['RESOLVED_ENTITY']['RECORDS']:
                    if dsrcRecord['INTERNAL_ID'] == internalId:
                        bestEntity = resolvedEntity
                        bestRecord = dsrcRecord
                        break

        if not bestRecord or 'FEATURES' not in bestRecord:
            print('\nno features found for resolved entity %s, internal ID %s\n' % (entityId, internalId))
            return {}

        features = self.buildoutRecordFeatures(bestRecord['FEATURES'], bestEntity['RESOLVED_ENTITY']['FEATURES'])
        return features

    # -----------------------------
    def buildoutRecordFeatures(self, recordFeatures, featureData):
        features = {}
        for featRecord in recordFeatures:
            libFeatId = featRecord['LIB_FEAT_ID']
            usageType = featRecord.get('USAGE_TYPE','')
            if libFeatId not in features:
                features[featRecord['LIB_FEAT_ID']] = {}
                features[libFeatId]['ftypeId'] = -1
                features[libFeatId]['ftypeCode'] = 'unknown'
                features[libFeatId]['usageType'] = usageType
                features[libFeatId]['featDesc'] = 'missing %s' % libFeatId
                features[libFeatId]['isCandidate'] = 'N'
                features[libFeatId]['isScored'] = 'N'
                features[libFeatId]['entityCount'] = -1
                features[libFeatId]['candidateCapReached'] = 'N'
                features[libFeatId]['scoringCapReached'] = 'N'
                features[libFeatId]['scoringWasSuppressed'] = 'N'

        for ftypeCode in featureData:
            for distinctFeatureRecord in featureData[ftypeCode]:
                for featRecord in distinctFeatureRecord['FEAT_DESC_VALUES']:
                    libFeatId = featRecord['LIB_FEAT_ID']
                    if libFeatId in features:
                        features[libFeatId]['ftypeId'] = self.ftypeCodeLookup[ftypeCode]['FTYPE_ID']
                        features[libFeatId]['ftypeCode'] = ftypeCode
                        #--disabled here in favor of the record level usage type
                        #features[libFeatId]['usageType'] = distinctFeatureRecord.get('USAGE_TYPE','') 
                        features[libFeatId]['featDesc'] = featRecord['FEAT_DESC']
                        features[libFeatId]['isCandidate'] = featRecord['USED_FOR_CAND']
                        features[libFeatId]['isScored'] = featRecord['USED_FOR_SCORING']
                        features[libFeatId]['entityCount'] = featRecord['ENTITY_COUNT']
                        features[libFeatId]['candidateCapReached'] = featRecord['CANDIDATE_CAP_REACHED']
                        features[libFeatId]['scoringCapReached'] = featRecord['SCORING_CAP_REACHED']
                        features[libFeatId]['scoringWasSuppressed'] = featRecord['SUPPRESSED']

        return features

    # -----------------------------
    def whyAddMatchInfo(self, features, matchInfo):

        whyKey = {}
        whyKey['matchKey'] = matchInfo['WHY_KEY']
        whyKey['ruleCode'] = self.getRuleDesc(matchInfo['WHY_ERRULE_CODE'])

        #--update from candidate section of why
        if 'CANDIDATE_KEYS' in matchInfo:
            for ftypeCode in matchInfo['CANDIDATE_KEYS']:
                ftypeId = self.ftypeCodeLookup[ftypeCode]['FTYPE_ID']
                for featRecord in matchInfo['CANDIDATE_KEYS'][ftypeCode]:
                    libFeatId = featRecord['FEAT_ID']
                    if libFeatId not in features:
                        print('warning: candidate feature %s not in record!' % libFeatId)
                        continue
                    features[libFeatId]['ftypeCode'] = ftypeCode
                    features[libFeatId]['ftypeId'] = ftypeId
                    features[libFeatId]['wasCandidate'] = 'Yes'
                    features[libFeatId]['matchScore'] = 100
                    features[libFeatId]['matchLevel'] = 'SAME'

        #--update from scoring section of why
        for ftypeCode in matchInfo['FEATURE_SCORES']:
            ftypeId = self.ftypeCodeLookup[ftypeCode]['FTYPE_ID']
            bestScoreRecord = {}
            for featRecord in matchInfo['FEATURE_SCORES'][ftypeCode]:
                #--BUG WHERE INBOUND/CANDIDATE IS SOMETIMES REVERSED...  
                if featRecord['INBOUND_FEAT_ID'] in features:
                    libFeatId = featRecord['INBOUND_FEAT_ID']
                    libFeatDesc = featRecord['INBOUND_FEAT']
                    matchedFeatId = featRecord['CANDIDATE_FEAT_ID']
                    matchedFeatDesc = featRecord['CANDIDATE_FEAT']
                elif featRecord['CANDIDATE_FEAT_ID'] in features:
                    #print(entityId, featRecord)
                    #pause()
                    libFeatId = featRecord['CANDIDATE_FEAT_ID']
                    libFeatDesc = featRecord['CANDIDATE_FEAT']
                    matchedFeatId = featRecord['INBOUND_FEAT_ID']
                    matchedFeatDesc = featRecord['INBOUND_FEAT']
                else:
                    print('warning: scored feature %s not in either record!' % libFeatId)
                    continue   

                featRecord = self.whySetMatchScore(featRecord)
                matchScore = featRecord['MATCH_SCORE']
                matchScoreDisplay = featRecord['MATCH_SCORE_DISPLAY']
                matchLevel = featRecord['SCORE_BUCKET']
                featBehavior = featRecord['SCORE_BEHAVIOR']

                if 'matchScore' not in bestScoreRecord or matchScore > bestScoreRecord['matchScore']:
                    bestScoreRecord['libFeatId'] = libFeatId
                    bestScoreRecord['matchScore'] = matchScore
                    bestScoreRecord['matchScoreDisplay'] = matchScoreDisplay
                    bestScoreRecord['matchLevel'] = matchLevel
                    bestScoreRecord['matchedFeatId'] = matchedFeatId
                    bestScoreRecord['matchedFeatDesc'] = matchedFeatDesc
                    bestScoreRecord['featBehavior'] = featBehavior

            if bestScoreRecord: # and bestScoreRecord['libFeatId'] in features) or not : #--adjusted for how
                libFeatId = bestScoreRecord['libFeatId']
                if libFeatId not in features:   #--adjusted for how
                    features[libFeatId] = {}
                features[libFeatId]['libFeatId'] = libFeatId
                features[libFeatId]['ftypeId'] = ftypeId
                features[libFeatId]['ftypeCode'] = ftypeCode
                features[libFeatId]['wasScored'] = 'Yes'
                features[libFeatId]['matchScore'] = bestScoreRecord['matchScore']
                features[libFeatId]['matchScoreDisplay'] = bestScoreRecord['matchScoreDisplay']
                features[libFeatId]['matchLevel'] = bestScoreRecord['matchLevel']
                features[libFeatId]['matchedFeatId'] = bestScoreRecord['matchedFeatId']
                features[libFeatId]['matchedFeatDesc'] = bestScoreRecord['matchedFeatDesc']
                features[libFeatId]['featBehavior'] = bestScoreRecord['featBehavior']
 
        return whyKey, features

    # -----------------------------
    def whySetMatchScore(self, featRecord):
        if 'GNR_FN' in featRecord:
            matchScore = featRecord['GNR_FN']
            if 'GNR_ON' in featRecord and featRecord['GNR_ON'] >= 0:
                matchScoreDisplay = 'org:%s' % featRecord['GNR_ON']
            else:
                matchScoreDisplay = 'full:%s' % featRecord['GNR_FN']
                if 'GNR_GN' in featRecord and featRecord['GNR_GN'] >= 0:
                    matchScoreDisplay += '|giv:%s' % featRecord['GNR_GN']
                if 'GNR_SN' in featRecord and featRecord['GNR_SN'] >= 0:
                    matchScoreDisplay += '|sur:%s' % featRecord['GNR_SN']
        elif 'BT_FN' in featRecord:
            matchScore = featRecord['BT_FN']
            if 'BT_ON' in featRecord and featRecord['BT_ON'] > 0:
                matchScoreDisplay = 'org:%s' % featRecord['BT_ON']
            else:
                matchScoreDisplay = 'full:%s' % featRecord['BT_FN']
        else:
            matchScore = featRecord['FULL_SCORE']
            matchScoreDisplay = 'full:' + str(featRecord['FULL_SCORE'])

        featRecord['MATCH_SCORE'] = matchScore
        featRecord['MATCH_SCORE_DISPLAY'] = matchScoreDisplay

        return featRecord

    def help_how(self):
        entity_id = colorize('<entity_id>', self.colors['entityid'])
        print(textwrap.dedent(f'''\

            Shows shows how the records in a single entity came together.

            {colorize('Syntax:', self.colors['highlight1'])}
                how {entity_id}               (shows the stats and brief view)
                how {entity_id} stats         (shows the stats view)
                how {entity_id} brief         (shows the brief view)
                how {entity_id} full          (shows the full entity at each step)

            {colorize('How to read:', self.colors['highlight1'])}
                A how report documents each step of the resoution process for an entity so if 
                an entity has 100s records there will be 100s of steps. Each step will either 
                create a virtual entity, add to it or combine it with other virtual entities 
                that may have gotten created along the way.  

                For instance, there may be a set of records (a virtual entity) that match on name 
                and address and another set that match on name and phone before a record with the 
                same name, address and phone combines the two virtual entities into one!

            {colorize('Pro tip!', self.colors['good'])}
                The statistics or (stats) section helps you locate key resolution steps based on 
                the step type, certain principles or match keys, or even by the most or least 
                common features. Try using the slash (/) key to search for an interesting step,
                match key or feature found in the statistics section to find out when it happened
                in the resolution process.

            '''))

    # -----------------------------
    def do_how(self,arg):

        #--no return code if called direct
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'

        if apiVersion['VERSION'][0:1] < '3':
            print('\nhow is only available in version 3.0 and higher\n')
            return -1 if calledDirect else 0

        if not arg:
            self.help_how()
            return -1 if calledDirect else 0

        arg = arg.lower()
        how_display_level = 'stats+brief'
        for level in ['detail', 'full', 'brief', 'stats']:
            if level in arg:
                how_display_level = level
                arg = arg.replace(level,'')

        try: 
            entityId = int(arg)
        except:
            print(f'\n invalid syntax: {arg} \n')
            self.help_how()
            return -1 if calledDirect else 0

        #--do get first
        getFlagList = []
        getFlagList.append('G2_ENTITY_INCLUDE_ENTITY_NAME')
        getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
        getFlagList.append('G2_ENTITY_OPTION_INCLUDE_FEATURE_STATS')
        getFlagList.append('G2_ENTITY_INCLUDE_RECORD_FEATURE_IDS')
        getFlagBits = self.computeApiFlags(getFlagList)
        apiCall = f'getEntityByEntityIDV2({arg}, {getFlagBits}, response)' 
        try: 
            response = bytearray()
            retcode = g2Engine.getEntityByEntityIDV2(int(arg), getFlagBits, response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print('\n' + str(err) + '\n')
            return -1 if calledDirect else 0
        json_data = json.loads(response)
        if debugOutput:
            showApiDebug('get', apiCall, getFlagList, json_data if response else '{}')
        getEntityData = json_data 

        stat_pack = {'steps': {}, 'features': {}, 'rules': {}, 'ftype_counter': {}, 'rule_counter': {}}

        #--build record feature matrix
        total_record_count = 0
        total_feature_count = 0
        features_by_record = {}
        for recordData in getEntityData['RESOLVED_ENTITY']['RECORDS']:
            total_record_count += 1
            if recordData['DATA_SOURCE'] not in features_by_record:
                features_by_record[recordData['DATA_SOURCE']] = {}
            features_by_record[recordData['DATA_SOURCE']][recordData['RECORD_ID']] = \
                self.buildoutRecordFeatures(recordData['FEATURES'], getEntityData['RESOLVED_ENTITY']['FEATURES'])

            #--accumulate feature stats
            for lib_feat_id in features_by_record[recordData['DATA_SOURCE']][recordData['RECORD_ID']]:
                feature_data = features_by_record[recordData['DATA_SOURCE']][recordData['RECORD_ID']][lib_feat_id]
                ftype_id = feature_data['ftypeId']
                counter_display = self.feature_counter_display(feature_data)
                feat_desc = f"{colorize(lib_feat_id, 'dim')}: {feature_data['featDesc']} {counter_display}"

                if ftype_id not in stat_pack['features']:
                    stat_pack['features'][ftype_id] = {}
                if ftype_id not in stat_pack['ftype_counter']:
                    stat_pack['ftype_counter'][ftype_id] = {}
                    stat_pack['ftype_counter'][ftype_id]['featureCount'] = 0
                    stat_pack['ftype_counter'][ftype_id]['candidateCapReached'] = 0
                    stat_pack['ftype_counter'][ftype_id]['scoringCapReached'] = 0
                    stat_pack['ftype_counter'][ftype_id]['scoringWasSuppressed'] = 0
                if feat_desc not in stat_pack['features'][ftype_id]:
                    total_feature_count += 1 
                    stat_pack['features'][ftype_id][feat_desc] = 1
                    stat_pack['ftype_counter'][ftype_id]['featureCount'] += 1
                    for threshold in ['candidateCapReached','scoringCapReached','scoringWasSuppressed']:
                        if feature_data[threshold] == 'Y':
                            stat_pack['ftype_counter'][ftype_id][threshold] += 1
                else:
                    stat_pack['features'][ftype_id][feat_desc] += 1

        howFlagList = ['G2_WHY_ENTITY_DEFAULT_FLAGS', 'G2_SEARCH_INCLUDE_FEATURE_SCORES']
        howFlagBits = self.computeApiFlags(howFlagList)
        try:
            response = bytearray()
            retcode = g2Engine.howEntityByEntityIDV2(entityId, howFlagBits, response)
            response = response.decode() if response else ''
        except G2Exception as err:
            print('\n' + str(err) + '\n')
            return -1 if calledDirect else 0
        if len(response) == 0:
            return -1 if calledDirect else 0
        json_data = json.loads(response)
        if debugOutput:
            apiCall = f'howEntityByEntityIDV2({entityId}, {howFlagBits}, response)'
            showApiDebug('howEntity', apiCall, howFlagList, json_data)

        root_node_id = 'FINAL_STATE'
        root_node = Node(root_node_id)
        tree_nodes = {root_node_id: root_node}

        #--notate steps and create aggregate dictionary
        step_count = 0
        aggregate_nodes = {}
        resolution_steps = {}
        for step_data in json_data['HOW_RESULTS']['RESOLUTION_STEPS']:
            step_count += 1
            step_num = step_data['STEP']
            for virtual_entity_num in ['VIRTUAL_ENTITY_1', 'VIRTUAL_ENTITY_2']:
                step_data[virtual_entity_num].update(self.get_virtual_entity_data(step_data[virtual_entity_num], features_by_record))

            step_data['singleton_nodes'] = []
            step_data['aggregate_nodes'] = []
            for virtual_entity in ['VIRTUAL_ENTITY_1', 'VIRTUAL_ENTITY_2']:
                if step_data[virtual_entity]['node_type'] == 'singleton':
                    step_data['singleton_nodes'].append(step_data[virtual_entity]['VIRTUAL_ENTITY_ID'])
                else:
                    step_data['aggregate_nodes'].append(step_data[virtual_entity]['VIRTUAL_ENTITY_ID'])

            if len(step_data['singleton_nodes']) == 2:
                step_data['step_type'] = 'Create virtual entity'
            elif len(step_data['aggregate_nodes']) == 2:
                step_data['step_type'] = 'Combine virtual entities'
            else:
                step_data['step_type'] = 'Add record to virtual entity'

            if step_data['step_type'] not in stat_pack['steps']:
                stat_pack['steps'][step_data['step_type']] = 1
            else:
                stat_pack['steps'][step_data['step_type']] += 1

            resolution_steps[step_num] = step_data
            new_virtual_id = step_data.get('RESULT_VIRTUAL_ENTITY_ID', None)
            if new_virtual_id:
                if new_virtual_id in aggregate_nodes:
                    print(json.dumps(step_data, indent=4))
                    print(f'\nunexpected: multiple steps for {new_virtual_id} {step_num} and ' + aggregate_nodes[new_virtual_id]['final_step'])
                    input('wait')
                aggregate_nodes[new_virtual_id] = {'final_step': step_num, 'all_steps': []}

        #--start from the end and combine the prior steps that just add another singleton 
        render_node_list = []
        if json_data['HOW_RESULTS']['RESOLUTION_STEPS']: #--bypass if no resolution steps taken
            for final_virtual_data in json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES']:
                final_virtual_id = final_virtual_data['VIRTUAL_ENTITY_ID']
                render_node_list.append({'node_id': final_virtual_id, 'parent_node': 'root'})

                current_aggregate_list = [final_virtual_id]
                while current_aggregate_list:
                    current_node_id = current_aggregate_list[-1]

                    #--keep going down chain until two singletons or two aggregates
                    aggregate_node_id = current_node_id
                    while True:
                        prior_step = aggregate_nodes[aggregate_node_id]['final_step']
                        aggregate_nodes[current_node_id]['all_steps'].append(prior_step)
                        if len(resolution_steps[prior_step]['aggregate_nodes']) == 1: 
                            aggregate_node_id = resolution_steps[prior_step]['aggregate_nodes'][0]
                        else:
                            break

                    #--done with this aggregate
                    current_aggregate_list.pop()

                    #--if ended on step with two aggregates, each must be traversed
                    if len(resolution_steps[prior_step]['aggregate_nodes']) == 2:
                        for aggregate_node_id in resolution_steps[prior_step]['aggregate_nodes']:
                            current_aggregate_list.append(aggregate_node_id)
                            render_node_list.append({'node_id': aggregate_node_id, 'parent_node': current_node_id})

        #--start rendering nodes
        root_node = Node('root')
        node_dict = {'root': root_node}
        for render_node_data in render_node_list:

            this_node_id = render_node_data['node_id']
            this_node = Node(this_node_id)
            node_dict[this_node_id] = this_node
            node_dict[render_node_data['parent_node']].add_child(this_node)

            colored_node_id = colorize(this_node_id, self.colors['entityid'])
            if render_node_data['parent_node'] == 'root':
                num_final_nodes = len(json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES'])
                this_node_index = 0
                for final_state_data in json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES']:
                    this_node_index += 1
                    if final_state_data['VIRTUAL_ENTITY_ID'] == this_node_id:
                        break
                if num_final_nodes == 1:
                    this_node.node_desc = colorize(f"{colored_node_id}: final entity", 'dim')
                else:
                    this_node.node_desc = colorize(f"{colored_node_id}: final entity {this_node_index} of {num_final_nodes}", 'dim')
            else:
                this_node.node_desc = colorize(f"{colored_node_id}: interim entity", 'dim')

            #--go through all the steps that built this node
            for step_num in sorted(aggregate_nodes[this_node_id]['all_steps'], reverse=True):
                step_data = resolution_steps[step_num]

                step_node = Node(step_num)
                step_node.node_desc = 'Step ' + str(step_num) + ': ' + step_data['step_type']
                this_node.add_child(step_node)

                #--always ensure lone singleton is on the left
                if step_data['VIRTUAL_ENTITY_1']['node_type'] != 'singleton' and step_data['VIRTUAL_ENTITY_2']['node_type'] == 'singleton':
                    left_virtual_entity = 'VIRTUAL_ENTITY_2'
                    right_virtual_entity = 'VIRTUAL_ENTITY_1'
                else:
                    left_virtual_entity = 'VIRTUAL_ENTITY_1'
                    right_virtual_entity = 'VIRTUAL_ENTITY_2'

                left_features = step_data[left_virtual_entity]['features']
                right_features = step_data[right_virtual_entity]['features']

                step_data['MATCH_INFO']['WHY_KEY'] = step_data['MATCH_INFO']['MATCH_KEY']
                step_data['MATCH_INFO']['WHY_ERRULE_CODE'] = step_data['MATCH_INFO']['ERRULE_CODE']
                why_key1, left_features = self.whyAddMatchInfo(left_features, step_data['MATCH_INFO'])
                why_key2, right_features = self.whyAddMatchInfo(right_features, step_data['MATCH_INFO'])
                step_data['MATCH_INFO']['matchKey'] = step_data['MATCH_INFO']['MATCH_KEY']
                step_data['MATCH_INFO']['ruleCode'] = self.getRuleDesc(step_data['MATCH_INFO']['ERRULE_CODE'])
                formatted_match_key, formatted_errule_code = formatMatchData(step_data['MATCH_INFO'], self.colors).split('\n ')
                step_node.node_desc += f" on {formatted_match_key} {formatted_errule_code}"

                if formatted_errule_code not in stat_pack['rules']:
                    stat_pack['rules'][formatted_errule_code] = {}
                    stat_pack['rule_counter'][formatted_errule_code] = 1
                else:
                    stat_pack['rule_counter'][formatted_errule_code] += 1
                if formatted_match_key not in stat_pack['rules'][formatted_errule_code]:
                    stat_pack['rules'][formatted_errule_code][formatted_match_key] = 1
                else: 
                    stat_pack['rules'][formatted_errule_code][formatted_match_key] += 1

                #--find the best matching record for each side
                #-- to make selection of best matching feature less arbitrary
                left_matching_record_list = {}
                right_matching_record_list = {}
                for lib_feat_id in left_features:
                    if left_features[lib_feat_id].get('wasScored', 'No') == 'Yes':
                        for record_key in left_features[lib_feat_id]['record_list']:
                            if record_key not in left_matching_record_list:
                                left_matching_record_list[record_key] = []
                            left_matching_record_list[record_key].append(lib_feat_id)

                        matched_feat_id = left_features[lib_feat_id]['matchedFeatId']
                        for record_key in right_features[matched_feat_id]['record_list']:
                            if record_key not in right_matching_record_list:
                                right_matching_record_list[record_key] = []
                            right_matching_record_list[record_key].append(matched_feat_id)
                best_left_record_key = sorted(sorted([{'key': i, 'len': len(left_matching_record_list[i])} for i in left_matching_record_list], key=lambda k: k['key']), key=lambda k: k['len'], reverse=True)[0]['key']
                best_right_record_key = sorted(sorted([{'key': i, 'len': len(right_matching_record_list[i])} for i in right_matching_record_list], key=lambda k: k['key']), key=lambda k: k['len'], reverse=True)[0]['key']

                #--gather the features to display by type for each side
                features_by_type = {}
                for side_data in [['left', left_features, right_features, best_left_record_key, best_right_record_key], 
                                  ['right', right_features, left_features, best_right_record_key, best_left_record_key]]:
                    side = side_data[0]
                    features1 = side_data[1]
                    features2 = side_data[2]
                    best_record_key1 = side_data[3]
                    best_record_key2 = side_data[4]

                    for lib_feat_id in features1:
                        feature_data = features1[lib_feat_id]

                        ftype_id = feature_data['ftypeId']
                        if ftype_id not in features_by_type:
                            features_by_type[ftype_id] = {'left': [], 'right': []}

                        #--get the best record keys for each side
                        matched_feat_id = feature_data.get('matchedFeatId')
                        if matched_feat_id:
                            if best_record_key1 in features1[lib_feat_id]['record_list']:
                                feature_data['record_key1'] = best_record_key1
                            else: 
                                feature_data['record_key1'] = features1[lib_feat_id]['record_list'][0]
                            if best_record_key2 in features2[matched_feat_id]['record_list']:
                                feature_data['record_key2'] = best_record_key2
                            else: 
                                feature_data['record_key2'] = features2[matched_feat_id]['record_list'][0]

                        #--skip unmatched if not showing full detail
                        elif how_display_level != 'full':
                            continue

                        feature_data = self.whyFormatFeature(feature_data, step_data['MATCH_INFO'])
                        features_by_type[ftype_id][side].append(feature_data)

                colored_virtual_id1 = colorize(step_data[left_virtual_entity]['VIRTUAL_ENTITY_ID'], self.colors['entityid'] + ',dim')
                colored_virtual_id2 = colorize(step_data[right_virtual_entity]['VIRTUAL_ENTITY_ID'], self.colors['entityid'] + ',dim')

                if 'brief' in how_display_level:
                    step_node.node_text = f"{colored_virtual_id1} {step_data[left_virtual_entity]['colored_desc']} {step_data[left_virtual_entity]['entity_name']}"
                    if not step_data['step_type'].startswith('Add'):
                        step_node.node_text += f"\n{colored_virtual_id2} {step_data[right_virtual_entity]['colored_desc']} {step_data[right_virtual_entity]['entity_name']}"
                    for ftypeId in sorted(features_by_type.keys(), key=lambda k: self.featureSequence[k]):
                        for featureData in sorted(sorted(features_by_type[ftypeId]['left'], key=lambda k: (k['featDesc'])), key=lambda k: (k['sortOrder'])):
                            coloredFtypeCode = colorize(featureData['ftypeCode'], self.colors['rowtitle'])
                            coloredRecordKey1 = colorize(': '.join(featureData['record_key1'].split(self.dsrc_record_sep)), self.colors['datasource'])
                            coloredRecordKey2 = colorize(': '.join(featureData['record_key2'].split(self.dsrc_record_sep)), self.colors['datasource'])
                            coloredMatchScore = colorize(f"({featureData['matchScoreDisplay']})", featureData['featColor'])
                            score_node = Node(featureData['ftypeCode'])
                            score_node.node_desc = f"{coloredFtypeCode}: {coloredRecordKey1} - {featureData['featDesc']} | {coloredRecordKey2} - {featureData['matchedFeatDesc']} {coloredMatchScore}"
                            step_node.add_child(score_node)
                    score_node.node_text = ' '
                else:
                    row_title = colorize('VIRTUAL_ID', 'dim')
                    tblTitle = None
                    tblColumns = []
                    tblColumns.append({'name': row_title, 'width': 20, 'align': 'left'})
                    tblColumns.append({'name': colored_virtual_id1, 'width': 75, 'align': 'left'})
                    tblColumns.append({'name': colorize('scores', 'dim'), 'width': 10, 'align': 'center'})
                    tblColumns.append({'name': colored_virtual_id2, 'width': 75, 'align': 'left'})
                    tblRows = []

                    row_title = colorize('DATA_SOURCES', self.colors['rowtitle'])
                    tblRow = [row_title]
                    for virtual_entity_data in [[left_virtual_entity, best_left_record_key], 
                                                [right_virtual_entity, best_right_record_key]]:
                        virtual_entity = virtual_entity_data[0]
                        best_record_key = virtual_entity_data[1]
                        if step_data[virtual_entity]['node_type'] == 'singleton':
                            dsrc_display = step_data[virtual_entity]['colored_desc']
                        else:
                            dsrc_display = step_data[virtual_entity]['node_desc'] + '\n best: ' + colorize(': '.join(best_record_key.split(self.dsrc_record_sep)), self.colors['datasource'])
                        tblRow.append(dsrc_display)
                    tblRow.insert(2, '') #--for score column
                    tblRows.append(tblRow)

                    for ftypeId in sorted(features_by_type.keys(), key=lambda k: self.featureSequence[k]):
                        if not features_by_type[ftypeId]['left'] and not features_by_type[ftypeId]['right']:
                            continue #-- removes unscored if not full
                        ftype_code = self.ftypeLookup[ftypeId]['FTYPE_CODE']
                        colored_ftype_code = colorize(ftype_code, self.colors['rowtitle'])

                        #--get the right side values
                        scored_right = {}
                        unscored_right = []
                        for feature_data in sorted(sorted(features_by_type[ftypeId]['right'], key=lambda k: (k['featDesc'])), key=lambda k: (k['sortOrder'])):
                            if feature_data.get('wasScored'):
                                scored_right[feature_data['libFeatId']] = feature_data
                            else:
                                unscored_right.append(feature_data['formattedFeatDesc1'])

                        #--add all the scored ones from the lefts point of view
                        unscored_left = []
                        for feature_data in sorted(sorted(features_by_type[ftypeId]['left'], key=lambda k: (k['featDesc'])), key=lambda k: (k['sortOrder'])):
                            if feature_data.get('wasScored'):
                                feature_score = '\n'.join(colorize(item, feature_data['featColor']) for item in feature_data['matchScoreDisplay'].split('|'))

                                feature_desc1 = feature_data['formattedFeatDesc1'] 
                                if step_data[left_virtual_entity]['node_type'] != 'singleton':
                                    from_desc = 'from: ' + colorize(': '.join(feature_data['record_key1'].split(self.dsrc_record_sep)), self.colors['datasource'])
                                    if feature_data['record_key1'] == best_left_record_key:
                                        from_desc = colorize(from_desc, 'dim')
                                    feature_desc1 += '\n ' + from_desc

                                feature_desc2 = scored_right[feature_data['matchedFeatId']]['formattedFeatDesc1'] 
                                if step_data[right_virtual_entity]['node_type'] != 'singleton':
                                    from_desc = 'from: ' + colorize(': '.join(feature_data['record_key2'].split(self.dsrc_record_sep)), self.colors['datasource'])
                                    if feature_data['record_key2'] == best_right_record_key:
                                        from_desc = colorize(from_desc, 'dim')
                                    feature_desc2 += '\n ' + from_desc
                 
                                tblRows.append([colored_ftype_code, feature_desc1, feature_score, feature_desc2])
                            else:
                                unscored_left.append(feature_data['formattedFeatDesc1'])

                        if unscored_right or unscored_left:
                            tblRows.append([colored_ftype_code, '\n'.join(unscored_left), '', '\n'.join(unscored_right)])

                    self.renderTable(tblTitle, tblColumns, tblRows, displayFlag = 'No')
                    step_node.node_text = self.currentRenderString

        #--render stats
        statistics_node = Node('statistics')
        statistics_node.node_desc = colorize('STATISTICS', 'bold')

        summary_node = Node('SUMMARY')
        summary_node.node_desc = self.how_format_statistic_header('SUMMARY')
        statistics_node.add_child(summary_node)

        for stat_data in [['Total record count', total_record_count], 
                          ['Total feature count', total_feature_count], 
                          ['Final entity count', len(root_node.children)]]:
            item_node = Node(stat_data[0])
            item_node.node_desc= self.how_format_statistic(stat_data[0], stat_data[1])
            summary_node.add_child(item_node)

        category_node = Node('steps')
        category_node.node_desc = self.how_format_statistic('Resolution steps', step_count)
        summary_node.add_child(category_node)
        for item in stat_pack['steps']:
            item_node = Node(item)
            item_node.node_desc = colorize(self.how_format_statistic(item, stat_pack['steps'][item]), 'italics')
            category_node.add_child(item_node)

        category_node = Node('rules')
        category_node.node_desc = colorize('PRINCIPLES', self.colors['highlight1'])
        statistics_node.add_child(category_node)
        for rule_info in sorted(stat_pack['rule_counter'].items() , key=lambda item: item[1],reverse=True):
            rule = rule_info[0]
            rule_node = Node(rule)
            rule_cnt = colorize(f"({rule_info[1]})", self.colors['highlight2'])
            rule_node.node_desc = f"{rule} {rule_cnt}"
            category_node.add_child(rule_node)
            for match_key_info in sorted(stat_pack['rules'][rule].items() , key=lambda item: item[1],reverse=True):
                match_key = match_key_info[0]
                match_key_node = Node(match_key)
                match_key_cnt = colorize(f"({match_key_info[1]})", self.colors['highlight2'])
                match_key_node.node_desc = f"{match_key} {match_key_cnt}"
                rule_node.add_child(match_key_node)

        category_node = Node('features')
        category_node.node_desc = colorize('FEATURES', self.colors['highlight1'])
        statistics_node.add_child(category_node)
        for ftype_id in sorted(stat_pack['features'], key=lambda k: self.featureSequence[k]):
            ftype_node = Node(ftype_id)
            ftype_cnt = colorize(f"({stat_pack['ftype_counter'][ftype_id]['featureCount']})", self.colors['highlight2'])
            ftype_node.node_desc = f"{colorize(self.ftypeLookup[ftype_id]['FTYPE_CODE'], self.colors['rowtitle'])} {ftype_cnt}"
            category_node.add_child(ftype_node)
            feat_desc_info_list = sorted(stat_pack['features'][ftype_id].items() , key=lambda item: item[1],reverse=True)
            cnt = 0
            for feat_desc_info in feat_desc_info_list:
                cnt += 1
                if cnt in (1, 2, len(feat_desc_info_list), len(feat_desc_info_list)-1):
                    feat_desc = feat_desc_info[0]
                    feat_node = Node(feat_desc)
                    feat_cnt = colorize(f"({feat_desc_info[1]})", self.colors['highlight2'])
                    if any(i in feat_desc for i in ['[~','[!','[#']):
                        feat_desc = colorize(feat_desc, 'dim')
                    feat_node.node_desc = f"{feat_desc} {feat_cnt}"
                    ftype_node.add_child(feat_node)
                elif cnt == 3 and len(feat_desc_info_list) > 4:
                    ftype_node.add_child(Node('~~~'))

        #--assemble report
        entity_name = getEntityData['RESOLVED_ENTITY'].get('ENTITY_NAME', 'name not mapped')
        how_report = colorize(f"\nHow report for entity: {entityId} - {entity_name}\n", self.colors['entityid'])

        if json_data['HOW_RESULTS']['FINAL_STATE'].get('NEED_REEVALUATION', 0) or \
           len(json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES']) > 1:
            how_report += colorize('REEVALUATION NEEDED!', self.colors['bad']) + '\n'

        if how_display_level != 'brief':
            how_report += '\n' + statistics_node.render_tree() 
 
        if how_display_level != 'stats' and root_node.children:  #--will be no children if singleton
            root_node.node_desc = 'RESOLUTION STEPS'
            how_report += '\n' + root_node.render_tree()
            #how_report += '\n' + colorize('RESOLUTION STEPS', 'bold')
            #for final_node in root_node.children:
            #    how_report += '\n' + final_node.render_tree()

        self.currentRenderString = how_report
        self.do_scroll('auto')

        return

    # -----------------------------
    def get_virtual_entity_data(self, raw_virtual_entity_data, features_by_record):
        virtual_entity_data = {'id': raw_virtual_entity_data['VIRTUAL_ENTITY_ID']}
        virtual_entity_data['record_count'] = 0
        virtual_entity_data['records'] = {}
        virtual_entity_data['features'] = {}
        bestNameCandidates = {'PRIMARY': '', 'OTHER': ''}
        for member_data in raw_virtual_entity_data['MEMBER_RECORDS']:
            for record in sorted(member_data['RECORDS'], key = lambda k: k['DATA_SOURCE'] + k['RECORD_ID']):
                virtual_entity_data['record_count'] += 1
                if record['DATA_SOURCE'] not in virtual_entity_data['records']:
                    virtual_entity_data['records'][record['DATA_SOURCE']] = []
                virtual_entity_data['records'][record['DATA_SOURCE']].append(record['RECORD_ID'])

                #--creates the master feature list for the virtual entity (accumulating which records have which features)
                record_key = record['DATA_SOURCE'] + self.dsrc_record_sep + record['RECORD_ID']
                for lib_feat_id in features_by_record[record['DATA_SOURCE']][record['RECORD_ID']]:
                    if lib_feat_id not in virtual_entity_data['features']:
                        virtual_entity_data['features'][lib_feat_id] = dict(features_by_record[record['DATA_SOURCE']][record['RECORD_ID']][lib_feat_id])
                        virtual_entity_data['features'][lib_feat_id]['record_list'] = [record_key]
                    elif record_key not in virtual_entity_data['features'][lib_feat_id]['record_list']:
                        virtual_entity_data['features'][lib_feat_id]['record_list'].append(record_key)

                    if virtual_entity_data['features'][lib_feat_id]['ftypeCode'] == 'NAME':
                        thisName = virtual_entity_data['features'][lib_feat_id]['featDesc']
                        thisUsageType = 'PRIMARY' if virtual_entity_data['features'][lib_feat_id]['usageType'] == 'PRIMARY' else 'OTHER'
                        if len(thisName) > len(bestNameCandidates[thisUsageType]):
                            bestNameCandidates[thisUsageType] = thisName
        virtual_entity_data['entity_name'] = bestNameCandidates['PRIMARY'] if bestNameCandidates['PRIMARY'] else bestNameCandidates['OTHER']

        #--a member is an obs_ent, despite how many records it has
        if len(raw_virtual_entity_data['MEMBER_RECORDS']) == 1:
            additional_note = ''
            if virtual_entity_data['record_count'] > 1: #--its got addtional pure dupes
                additional_note = colorize(' +' + str(virtual_entity_data['record_count'] - 1) + ' pure dupes', 'dim')

            virtual_entity_data['node_type'] = 'singleton'
            record = raw_virtual_entity_data['MEMBER_RECORDS'][0]['RECORDS'][0]
            virtual_entity_data['node_desc'] = record['DATA_SOURCE'] + ': ' + record['RECORD_ID'] + additional_note
            virtual_entity_data['colored_desc'] = colorize(record['DATA_SOURCE'] + ': ' + record['RECORD_ID'] + additional_note, self.colors['datasource']) 

        else:
            virtual_entity_data['node_type'] = 'aggregate'
            virtual_entity_data['node_desc'] = ' | '.join(\
                colorize(ds + ' (' + str(len(virtual_entity_data['records'][ds])) + ')', self.colors['datasource']) \
                for ds in sorted(virtual_entity_data['records'].keys()))
            virtual_entity_data['colored_desc'] = virtual_entity_data['node_desc']

        return virtual_entity_data

    # -----------------------------
    def how_format_statistic_header(self, header):
        return colorize(header, self.colors['highlight1'])

    # -----------------------------
    def how_format_statistic(self, stat, cnt):
        return stat + ' ' + colorize('(' + str(cnt) + ')', self.colors['highlight2'])


    # -----------------------------
    def do_score(self, arg): 
        '\nCompares any two features and shows the scores returned.\n' \
        '\nSyntax:' \
        '\n\tscore [{"name_last": "Smith", "name_first": "Joseph"}, {"name_last": "Smith", "name_first": "Joe"}]' \
        '\n\tscore [{"addr_full": "111 First St, Anytown, USA"}, {"addr_full": "111 First Street, Anytown"}]' \
        '\n\tscore [{"passport_number": "1231234", "passport_country": "US"}, {"passport_number": "1231234", "passport_country": "USA"}]'

        if not argCheck('do_score', arg, self.do_score.__doc__):
            return

        #--see if they gave us json
        try: 
            jsonData = json.loads(arg)
            record1json = dictKeysUpper(jsonData[0])
            record2json = dictKeysUpper(jsonData[1])
        except:
            print('json parameters are invalid, see example in help')
            return

        #--use the test data source and entity type
        record1json['TRUSTED_ID_NUMBER'] = 'SCORE_TEST'
        record2json['TRUSTED_ID_NUMBER'] = 'SCORE_TEST'

        #--add the records
        try: 
            retcode = g2Engine.addRecord('TEST', 'SCORE_RECORD_1', json.dumps(record1json))
            retcode = g2Engine.addRecord('TEST', 'SCORE_RECORD_2', json.dumps(record2json))
        except G2Exception as err:
            print(str(err))
            return

        self.do_why('TEST SCORE_RECORD_1 TEST SCORE_RECORD_2')

        #--delete the two temporary records 
        try: 
            retcode = g2Engine.deleteRecord('TEST', 'SCORE_RECORD_1')
            retcode = g2Engine.deleteRecord('TEST', 'SCORE_RECORD_2')
        except G2Exception as err:
            print(str(err))
            return

        return

    # -----------------------------
    def renderTable(self, tblTitle, tblColumns, tblRows, **kwargs):

        #--display flags (start/append/done) allow for multiple tables to be displayed together and scrolled as one
        #--such as an entity and its relationships

        #--possible kwargs
        displayFlag = kwargs['displayFlag'] if 'displayFlag' in kwargs else None 
        titleColor = kwargs['titleColor'] if 'titleColor' in kwargs else self.colors['tableTitle']
        titleJustify = kwargs['titleJustify'] if 'titleJustify' in kwargs else 'l' #--left
        headerColor = kwargs['headerColor'] if 'headerColor' in kwargs else self.colors['columnHeader']

        #--setup the table
        tableWidth = 0
        columnHeaderList = []
        for i in range(len(tblColumns)):
            tableWidth += tblColumns[i]['width']
            tblColumns[i]['name'] = str(tblColumns[i]['name'])
            columnHeaderList.append(tblColumns[i]['name'])
        #tableObject = ColoredTable(title_color=titleColor, header_color=headerColor, title_justify=titleJustify)
        tableObject = PrettyTable()

        #tableObject.title = tblTitle
        tableObject.hrules = PRETTY_TABLE_ALL
        if pretty_table_style_available: 
            tableObject.set_style(SINGLE_BORDER)
        else:
            tableObject.hrules = PRETTY_TABLE_ALL
            tableObject.horizontal_char = "-"
            tableObject.vertical_char = "¦"
            tableObject.junction_char = "+"
            tableObject.top_junction_char = "-"
            tableObject.bottom_junction_char = "-"
            tableObject.right_junction_char = "¦"
            tableObject.left_junction_char = "+"
            tableObject.top_right_junction_char = "+"
            tableObject.top_left_junction_char = "+"
            tableObject.bottom_right_junction_char = "+"
            tableObject.bottom_left_junction_char = "+"
        tableObject.field_names = columnHeaderList
 
        totalRowCnt = 0
        for row in tblRows:
            totalRowCnt += 1
            row[0] = '\n'.join([i for i in str(row[0]).split('\n')])
            if self.usePrettyTable:
                tableObject.add_row(row)
            else:
                tableObject.append_row(row)

        #--format with data in the table
        for columnData in tblColumns:
            tableObject.max_width[str(columnData['name'])] = columnData['width']
            tableObject.align[str(columnData['name'])] = columnData['align'][0:1].lower()

        #--write to a file so can be viewed with less
        #--also write to the lastTableData variable in case cannot write to file
        fmtTableString = ''
        if tblTitle:
            fmtTableString = colorize(tblTitle, titleColor) + '\n'
        fmtTableString += tableObject.get_string() + '\n'

        writeMode = 'w'
        if displayFlag in ('append', 'end'):
            fmtTableString = '\n' + fmtTableString 
            writeMode = 'a'

        if writeMode == 'w':
             self.currentRenderString = fmtTableString
        else:
             self.currentRenderString = self.currentRenderString + fmtTableString

        # display if a single table or done acculating tables to display
        if not displayFlag or displayFlag == 'end':
            print('')
            if self.currentReviewList:
                print(colorize(self.currentReviewList, 'bold'))
            self.do_scroll('auto')
        return

    # -----------------------------
    def do_scroll(self,arg):
        '\nLoads the last table rendered into the linux less viewer where you can use the arrow keys to scroll ' \
        '\n up and down, left and right, until you type Q to quit.\n'

        #--note: the F allows less to auto quit if output fits on screen
        #-- if they purposely went into scroll mode, we should not auto-quit!
        if arg == 'auto':  
            lessOptions = 'FMXSR'
        else:
            lessOptions = 'MXSR'

        #--try pipe to less on small enough files (pipe buffer usually 1mb and fills up on large entity displays)
        less = subprocess.Popen(["less", "-FMXSR"], stdin=subprocess.PIPE)
        try:
            less.stdin.write(self.currentRenderString.encode('utf-8'))
        except IOError:
            pass
        less.stdin.close()
        less.wait()

    # -----------------------------
    def do_export(self,arg):
        '\nExports the json records that make up the selected entities for debugging, reloading, etc.' \
        '\n\nSyntax:' \
        '\n\texport <entity_id>, <entity_id> degree <n> to <fileName> additive' \
        '\n\texport search to <fileName>' \
        '\n\texport search <search index> to <fileName>\n'
        if not argCheck('do_export', arg, self.do_export.__doc__):
            return

        print()

        entityList = []
        fileName = None
        maxDegree = 0
        additive = False

        arg = arg.replace(',', '')
        arglist = arg.split()
        i = 0
        while i < len(arglist):
            thisToken = arglist[i].upper()
            nextToken = arglist[i + 1] if i + 1 < len(arglist) else ''
            if thisToken == 'TO':
                if nextToken:
                    fileName = nextToken
                    i += 1

            elif thisToken == 'SEARCH':
                if nextToken.isdigit():
                    if int(nextToken) > len(self.lastSearchResult):
                        print('\n-invalid last search index\n')
                        return -1 if calledDirect else 0
                    else:
                        entityList.append(self.lastSearchResult[int(lastToken)-1])
                        i += 1
                else:
                    entityList = self.lastSearchResult
            elif thisToken == 'DEGREE':
                if nextToken.isdigit():
                    maxDegree = int(nextToken)
                    i += 1
            elif thisToken.upper().startswith('ADD'):
                additive = True

            elif thisToken.isdigit():
                entityList.append(int(thisToken))
            else:
                print(f'-unknown command token: {thisToken}')
            i += 1

        if not entityList:
            print('no entities selected!\n')
            return 

        if not fileName:
            if len(entityList) == 1:
                fileName = str(entityList[0]) + '.json'
            else:
                fileName = 'records.json'
            
        try: f = open(fileName, 'a' if additive else 'w')
        except IOError as err:
            print('cannot write to %s\n\t- %s' % (fileName, err))
            return

        getFlagList = []    
        if apiVersion['VERSION'][0:1] == '1':
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
        else:
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_DATA')
            getFlagList.append('G2_ENTITY_INCLUDE_RECORD_JSON_DATA')
            if maxDegree > 0:
                getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')
        getFlagBits = self.computeApiFlags(getFlagList)

        exportedEntityList = []
        recordCount = 0
        currentDegree = 0
        currentEntityList = entityList
        while currentDegree <= maxDegree:
            nextEntityList = []
            for entityId in currentEntityList:
                exportedEntityList.append(entityId)

                apiCall = f'getEntityByEntityIDV2({entityId})'
                try: 
                    response = bytearray()
                    retcode = g2Engine.getEntityByEntityIDV2(int(entityId), getFlagBits, response)
                    response = response.decode() if response else ''
                except G2Exception as err:
                    print('\n' + str(err) + '\n')
                if debugOutput:
                    showApiDebug('get', apiCall, getFlagList, json.loads(response) if response else '{}')

                jsonData = json.loads(response)
                for recordData in jsonData['RESOLVED_ENTITY']['RECORDS']:
                    f.write(json.dumps(recordData['JSON_DATA']) + '\n')
                    recordCount += 1

                if 'RELATED_ENTITIES' in jsonData:
                    for relatedData in jsonData['RELATED_ENTITIES']:
                        if relatedData['ENTITY_ID'] not in exportedEntityList and \
                           relatedData['ENTITY_ID'] not in nextEntityList:
                            nextEntityList.append(relatedData['ENTITY_ID'])

            currentDegree += 1
            if nextEntityList:
                currentEntityList = nextEntityList
            else:
                break

        f.close

        print(f'{recordCount} records written to {fileName}\n')

    # -----------------------------
    def getRuleDesc(self, erruleCode):
        return ('RULE ' + str(self.erruleCodeLookup[erruleCode]['ERRULE_ID']) + ': ' + erruleCode  if erruleCode in self.erruleCodeLookup else '')

    # -----------------------------
    def getConfigData(self, table, field = None, value = None):

        recordList = []
        for i in range(len(self.cfgData['G2_CONFIG'][table])):
            if field and value:
                if self.cfgData['G2_CONFIG'][table][i][field] == value:
                    recordList.append(self.cfgData['G2_CONFIG'][table][i])
            else:
                recordList.append(self.cfgData['G2_CONFIG'][table][i])
        return recordList

    # -----------------------------
    def xx_listAttributes(self,arg):  #--disabled
        '\n\tlistAttributes\n'

        print('')
        for attrRecord in sorted(self.getConfigData('CFG_ATTR'), key = lambda k: k['ATTR_ID']):
            print(self.getAttributeJson(attrRecord))
        print('')

    # -----------------------------
    def getAttributeJson(self, attributeRecord):

        if 'ADVANCED' not in attributeRecord:
            attributeRecord['ADVANCED'] = 0
        if 'INTERNAL' not in attributeRecord:
            attributeRecord['INTERNAL'] = 0
            
        jsonString = '{'
        jsonString += '"id": "%s"' % attributeRecord['ATTR_ID']
        jsonString += ', "attribute": "%s"' % attributeRecord['ATTR_CODE']
        jsonString += ', "class": "%s"' % attributeRecord['ATTR_CLASS']
        jsonString += ', "feature": "%s"' % attributeRecord['FTYPE_CODE']
        jsonString += ', "element": "%s"' % attributeRecord['FELEM_CODE']
        jsonString += ', "required": "%s"' % attributeRecord['FELEM_REQ'].title()
        jsonString += ', "default": "%s"' % attributeRecord['DEFAULT_VALUE']
        jsonString += ', "advanced": "%s"' % ('Yes' if attributeRecord['ADVANCED'] == 1 else 'No') 
        jsonString += ', "internal": "%s"' % ('Yes' if attributeRecord['INTERNAL'] == 1 else 'No')
        jsonString += '}'
        
        return jsonString

    # -----------------------------
    def isInternalAttribute(self, attrStr):
        if ':' in attrStr:
            attrStr = attrStr.split(':')[0]
        attrRecords = self.getConfigData('CFG_ATTR', 'ATTR_CODE', attrStr.upper())
        if attrRecords and attrRecords[0]['INTERNAL'].upper().startswith('Y'):
            return True
        return False 

    # -----------------------------
    def computeApiFlagsx(self, flagList):
            flagBits = 0
            for flagName in flagList:
                if apiVersion['VERSION'][0:1] > '2':
                    flagBits = flagBits | getattr(G2EngineFlags, flagName)
                else:
                    flagBits = flagBits | getattr(g2Engine, flagName)
            return flagBits

    # -----------------------------
    def computeApiFlags(self, flagList):
            if apiVersion['VERSION'][0:1] > '2':
                return G2EngineFlags.combine_flags(flagList)
            else:
                flagBits = 0
                for flagName in flagList:
                    flagBits = flagBits | getattr(g2Engine, flagName)
                return flagBits

# ===== utility functions =====

# -----------------------------
def colorizeAttribute(attrStr, color):
    if ':' in attrStr:
        attrName = attrStr[0:attrStr.find(':')+1]
        attrValue = attrStr[attrStr.find(':')+1:].strip()
        return colorize(attrName, color) + ' ' + attrValue
    else:
        return attrStr

# -----------------------------
def formatMatchData(matchDict, colorscheme = None):

    if not matchDict['matchKey']:
        matchStr = colorize('not found!', 'bg.red,fg.white')
    else:
        if colorscheme:
            matchKeySegments = []
            priorKey = ''
            keyColor = 'fg.green'
            for key in re.split('(\+|\-)', matchDict['matchKey']):
                if key in ('+',''): 
                    priorKey = '+'
                    keyColor = colorscheme['good']
                elif key == '-':
                    priorKey = '-'
                    keyColor = colorscheme['bad']
                else:
                    matchKeySegments.append(colorize(priorKey+key, keyColor))
            matchStr = ''.join(matchKeySegments)
        else:
            matchStr = matchDict['matchKey']

    if 'ruleCode' in matchDict:
        matchStr += ('\n ' + colorize('%s' % matchDict['ruleCode'], 'dim'))

    if 'entityId' in matchDict:
        matchStr += colorize(' to %s' % matchDict['entityId'], 'dim')

    return matchStr

#----------------------------------------
def showApiDebug(processName, apiCall, apiFlagList, jsonResponse):
    showDebug(processName, apiCall + '\n\t' + '\n\t'.join(apiFlagList) + '\n' + json.dumps(jsonResponse, indent=4))

#----------------------------------------
def showDebug(call, output=''):
    if debugOutput.upper() in ('S', 'SCR', 'SCREEN'):
        print('- %s -' % call)
        if type(output) == dict:
            print(json.dumps(output, indent=4))
        elif output: 
            print(output)
        print()
    else: 
        try:
            with open(debugOutput, 'a') as f:
                f.write('- %s - \n' % call)
                if type(output) == dict:
                    f.write(json.dumps(output))
                elif output: 
                    f.write(output)
                f.write('\n\n')

        except IOError as err:
            print('cannot write to %s - %s' % (debugOutput, err))
            return

#----------------------------------------
def pause(question='PRESS ENTER TO CONTINUE ...'):
    """ pause for debug purposes """
    try: input(question)
    except KeyboardInterrupt:
        global shutDown
        shutDown = True
    except: pass

def argCheck(func, arg, docstring):

    if len(arg.strip()) == 0:
        print('\nMissing argument(s) for %s, command syntax: %s \n' % (func, '\n\n' + docstring[1:]))
        return False
    else:
        return True

def argError(errorArg, error):

    printWithNewLines('Incorrect argument(s) or error parsing argument: %s' % errorArg, 'S')
    printWithNewLines('Error: %s' % error, 'E')

def fmtStatistic(amt):
    amt = int(amt)
    if amt > 1000000:
        return "{:,.2f}m".format(round(amt/1000000,2))
    else:
        return "{:,}".format(amt)

def pad(val, len):
    if type(val) != str:
        val = str(val)
    return (val + (' ' * len))[:len]

def lpad(val, len):
    if type(val) != str:
        val = str(val)
    return ((' ' * len) + val)[-len:]

def printWithNewLines(ln, pos=''):

    pos.upper()
    if pos == 'S' or pos == 'START' :
        print('\n' + ln)
    elif pos == 'E' or pos == 'END' :
        print(ln + '\n')
    elif pos == 'B' or pos == 'BOTH' :
        print('\n' + ln + '\n')
    else:
        print(ln)

def dictKeysUpper(dict):
    return {k.upper():v for k,v in dict.items()}

def showMeTheThings(data, loc=''):
    printWithNewLines('<---- DEBUG')
    printWithNewLines('Func: %s' % sys._getframe(1).f_code.co_name)
    if loc != '': printWithNewLines('Where: %s' % loc) 
    if type(data) == list:
        printWithNewLines(('[%s]\n' * len(data)) % tuple(data)) 
    else:
        printWithNewLines('Data: %s' % str(data))
    printWithNewLines('---->', 'E')

def removeFromHistory(idx = 0):
    if readline:
        if not idx:
            idx = readline.get_current_history_length()-1
        readline.remove_history_item(idx)

def _append_slash_if_dir(p):
    if p and os.path.isdir(p) and p[-1] != os.sep:
        return p + os.sep
    else:
        return p

def fuzzyCompare(ftypeCode, cfuncCode, str1, str2):

    if hasFuzzy and cfuncCode:
        if cfuncCode in ('GNR_COMP', 'BT_NAME_COMP', 'ADDR_COMP', 'GROUP_ASSOCIATION_COMP'):
            closeEnough = fuzz.token_set_ratio(str1, str2) >= 80
        elif cfuncCode in ('DOB_COMP'):
            if len(str1) == len(str2):
                closeEnough = fuzz.token_set_ratio(str1, str2) >= 90
            else:
                closeEnough = str1[0:max(len(str1), len(str2))] == str2[0:max(len(str1), len(str2))]
        elif cfuncCode in ('SSN_COMP'):
            closeEnough = fuzz.token_set_ratio(str1, str2) >= 90
        elif cfuncCode in ('ID_COMP'):
            closeEnough = fuzz.ratio(str1, str2) >= 90
        elif cfuncCode in ('PHONE_COMP'):
            closeEnough = str1[-7:] == str2[-7:]
            #closeEnough = ''.join(i for 1 in str1 if i.isdigit())[-7:] == ''.join(i for i in str2 if i.isdigit())[-7:]
        else:
            closeEnough = str1 == str2
    else:
            closeEnough = str1 == str2
    return closeEnough


# ===== The main function =====
if __name__ == '__main__':
    appPath = os.path.dirname(os.path.abspath(sys.argv[0]))

    #--defaults
    try: iniFileName = G2Paths.get_G2Module_ini_path() 
    except: iniFileName = ''

    #--capture the command line arguments
    argParser = argparse.ArgumentParser()
    argParser.add_argument('-c', '--config_file_name', dest='ini_file_name', default=iniFileName, help='name of the g2.ini file, defaults to %s' % iniFileName)
    argParser.add_argument('-s', '--snapshot_json_file', dest='snapshot_file_name', default=None, help='the name of a json statistics file computed by G2Snapshot.py')
    argParser.add_argument('-a', '--audit_json_file', dest='audit_file_name', default=None, help='the name of a json statistics file computed by G2Audit.py')
    argParser.add_argument('-D', '--debug_output', dest='debug_output', default=None, help='print raw api json to screen or <filename.txt>')
    argParser.add_argument('-H', '--histDisable', dest='histDisable', action='store_true', default=False, help='disable history file usage')

    args = argParser.parse_args()
    iniFileName = args.ini_file_name
    snapshotFileName = args.snapshot_file_name
    auditFileName = args.audit_file_name
    debugOutput = args.debug_output
    hist_disable = args.histDisable

    #--validate snapshot file if specified
    if snapshotFileName and not os.path.exists(snapshotFileName):
        print('\nSnapshot file %s not found\n' % snapshotFileName)
        sys.exit(1)

    #--validate audit file if specified
    if auditFileName and not os.path.exists(auditFileName):
        print('\nAudit file %s not found\n' % auditFileName)
        sys.exit(1)

    #--get parameters from ini file
    if not os.path.exists(iniFileName):
        print('\nAn ini file was not found, please supply with the -c parameter\n')
        sys.exit(1)
 
    splash = '\n  ____|  __ \\     \\    \n'
    splash += '  __|    |   |   _ \\   Senzing G2\n'
    splash += '  |      |   |  ___ \\  Exploratory Data Analysis\n'
    splash += ' _____| ____/ _/    _\\ \n'
    prompt = '(g2) '
    print(splash)

    #--get the version information
    try: 
        g2Product = G2Product()
        apiVersion = json.loads(g2Product.version())
    except G2Exception as err:
        print(err)
        sys.exit(1)

    #--try to initialize the g2engine
    try:
        g2Engine = G2Engine()
        iniParamCreator = G2IniParams()
        iniParams = iniParamCreator.getJsonINIParams(iniFileName)
        if apiVersion['VERSION'][0:1] == '2':
            g2Engine.initV2('G2Explorer', iniParams, False)
        else: #--eventually deprecate the above
            g2Engine.init('G2Explorer', iniParams, False)
    except G2Exception as err:
        print('\n%s\n' % str(err))
        sys.exit(1)

    #--get needed config data
    try: 
        g2ConfigMgr = G2ConfigMgr()
        if apiVersion['VERSION'][0:1] == '2':
            g2ConfigMgr.initV2('pyG2ConfigMgr', iniParams, False)
        else: #--eventually deprecate the above
            g2ConfigMgr.init('pyG2ConfigMgr', iniParams, False)
        defaultConfigID = bytearray() 
        g2ConfigMgr.getDefaultConfigID(defaultConfigID)
        defaultConfigDoc = bytearray() 
        g2ConfigMgr.getConfig(defaultConfigID, defaultConfigDoc)
        cfgData = json.loads(defaultConfigDoc.decode())
        g2ConfigMgr.destroy()
    except Exception as err:
        print('\n%s\n' % str(err))
        sys.exit(1)
    g2ConfigMgr.destroy()

    #--cmdloop()
    G2CmdShell().cmdloop()
    print('')

    #--cleanups
    g2Engine.destroy()

    sys.exit()

