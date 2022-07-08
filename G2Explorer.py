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
from contextlib import suppress

try:
    from prettytable import PrettyTable
    from prettytable import ALL as PRETTY_TABLE_ALL
    try:  # Supports both ptable and prettytable builds of prettytable (only prettytable has these styles)
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
    from G2IniParams import G2IniParams
    from senzing import G2ConfigMgr, G2Diagnostic, G2Engine, G2EngineFlags, G2Exception, G2Product
except:

    # Fall back to pre-Senzing-Python-SDK style of imports.
    try:
        import G2Paths
        from G2IniParams import G2IniParams
        from G2Product import G2Product
        from G2Config import G2Config
        from G2ConfigMgr import G2ConfigMgr
        from G2Diagnostic import G2Diagnostic
        from G2Engine import G2Engine
        from G2Exception import G2Exception
    except:
        print('\nPlease export PYTHONPATH=<path to senzing python directory>\n')
        sys.exit(1)

# ---------------------------
def execute_api_call(api_name, flag_list, parm_list):
    if api_version_major < 3:
        old_versions = {'getEntityByEntityID': 'getEntityByEntityIDV2',
                        'getEntityByRecordID': 'getEntityByRecordIDV2',
                        'searchByAttributes': 'searchByAttributesV2',
                        'whyEntityByEntityID': 'whyEntityByEntityIDV2',
                        'whyEntities': 'whyEntitiesV2',
                        'whyRecords': 'whyRecordsV2',
                        'findNetworkByEntityID': 'findNetworkByEntityIDV2'}
        if api_name in old_versions:
            api_name = old_versions[api_name]

    parm_list = parm_list if type(parm_list) == list else [parm_list]
    called_by = sys._getframe().f_back.f_code.co_name

    if not hasattr(g2Engine, api_name):
        raise Exception(f"{called_by}: {api_name} not valid in {api_version['BUILD_VERSION']}")

    if api_version_major > 2:
        try: flags = int(G2EngineFlags.combine_flags(flag_list))
        except Exception as err:
            raise Exception(f"{called_by}: {api_called} - {err}")

    else:
        flags = 0
        for flag_name in flag_list:
            if hasattr(g2Engine, flag_name):
                flags = flags | getattr(g2Engine, flag_name)
            else:
                raise Exception(f"{called_by}: {api_name} - {flag_name} flag not valid in {api_version['BUILD_VERSION']}")

    response = bytearray()
    if api_version_major > 2:
        parm_list += [response, flags]
    else:
        parm_list += [flags, response]
    api_called = f"{api_name}({', '.join(str(x) for x in parm_list)})"

    try:
        api_call = getattr(g2Engine, api_name)
        api_call(*parm_list)
        response_data = json.loads(response)
        if debugOutput:
            showDebug(called_by, api_called + '\n\t' + '\n\t'.join(flag_list) + '\n' + json.dumps(response_data, indent=4))
        return response_data
    except G2Exception as err:
        raise Exception(f"{called_by}: {api_called} - {err}")
    #except Exception as err:
    #    raise Exception(f"{called_by}: {api_called} - {err}")

# ==============================
class Colors:

    @classmethod
    def apply(cls, in_string, color_list=None):
        ''' apply list of colors to a string '''
        if color_list:
            prefix = ''.join([getattr(cls, i.strip().upper()) for i in color_list.split(',')])
            suffix = cls.RESET
            return f'{prefix}{in_string}{suffix}'
        return in_string

    @classmethod
    def set_theme(cls, theme):
        # best for dark backgrounds
        if theme.upper() == 'DEFAULT':
            cls.TABLE_TITLE = cls.FG_GREY42
            cls.ROW_TITLE = cls.FG_GREY42
            cls.COLUMN_HEADER = cls.FG_GREY42
            cls.ENTITY_COLOR = cls.FG_MEDIUMORCHID1
            cls.DSRC_COLOR = cls.FG_ORANGERED1
            cls.ATTR_COLOR = cls.FG_CORNFLOWERBLUE
            cls.GOOD = cls.FG_CHARTREUSE3
            cls.BAD = cls.FG_RED3
            cls.CAUTION = cls.FG_GOLD3
            cls.HIGHLIGHT1 = cls.FG_DEEPPINK4
            cls.HIGHLIGHT2 = cls.FG_DEEPSKYBLUE1
        elif theme.upper() == 'LIGHT':
            cls.TABLE_TITLE = cls.FG_LIGHTBLACK
            cls.ROW_TITLE = cls.FG_LIGHTBLACK
            cls.COLUMN_HEADER = cls.FG_LIGHTBLACK  # + cls.ITALICS
            cls.ENTITY_COLOR = cls.FG_LIGHTMAGENTA + cls.BOLD
            cls.DSRC_COLOR = cls.FG_LIGHTYELLOW + cls.BOLD
            cls.ATTR_COLOR = cls.FG_LIGHTCYAN + cls.BOLD
            cls.GOOD = cls.FG_LIGHTGREEN
            cls.BAD = cls.FG_LIGHTRED
            cls.CAUTION = cls.FG_LIGHTYELLOW
            cls.HIGHLIGHT1 = cls.FG_LIGHTMAGENTA
            cls.HIGHLIGHT2 = cls.FG_LIGHTCYAN
        elif theme.upper() == 'DARK':
            cls.TABLE_TITLE = cls.FG_LIGHTBLACK
            cls.ROW_TITLE = cls.FG_LIGHTBLACK
            cls.COLUMN_HEADER = cls.FG_LIGHTBLACK  # + cls.ITALICS
            cls.ENTITY_COLOR = cls.FG_MAGENTA + cls.BOLD
            cls.DSRC_COLOR = cls.FG_YELLOW + cls.BOLD
            cls.ATTR_COLOR = cls.FG_CYAN + cls.BOLD
            cls.GOOD = cls.FG_GREEN
            cls.BAD = cls.FG_RED
            cls.CAUTION = cls.FG_YELLOW
            cls.HIGHLIGHT1 = cls.FG_MAGENTA
            cls.HIGHLIGHT2 = cls.FG_CYAN

    # styles
    RESET = '\033[0m'
    BOLD = '\033[01m'
    DIM = '\033[02m'
    ITALICS = '\033[03m'
    UNDERLINE = '\033[04m'
    BLINK = '\033[05m'
    REVERSE = '\033[07m'
    STRIKETHROUGH = '\033[09m'
    INVISIBLE = '\033[08m'
    # foregrounds
    FG_BLACK = '\033[30m'
    FG_WHITE = '\033[97m'
    FG_BLUE = '\033[34m'
    FG_MAGENTA = '\033[35m'
    FG_CYAN = '\033[36m'
    FG_YELLOW = '\033[33m'
    FG_GREEN = '\033[32m'
    FG_RED = '\033[31m'
    FG_LIGHTBLACK = '\033[90m'
    FG_LIGHTWHITE = '\033[37m'
    FG_LIGHTBLUE = '\033[94m'
    FG_LIGHTMAGENTA = '\033[95m'
    FG_LIGHTCYAN = '\033[96m'
    FG_LIGHTYELLOW = '\033[93m'
    FG_LIGHTGREEN = '\033[92m'
    FG_LIGHTRED = '\033[91m'
    # backgrounds
    BG_BLACK = '\033[40m'
    BG_WHITE = '\033[107m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_YELLOW = '\033[43m'
    BG_GREEN = '\033[42m'
    BG_RED = '\033[41m'
    BG_LIGHTBLACK = '\033[100m'
    BG_LIGHTWHITE = '\033[47m'
    BG_LIGHTBLUE = '\033[104m'
    BG_LIGHTMAGENTA = '\033[105m'
    BG_LIGHTCYAN = '\033[106m'
    BG_LIGHTYELLOW = '\033[103m'
    BG_LIGHTGREEN = '\033[102m'
    BG_LIGHTRED = '\033[101m'
    # extended
    FG_DARKORANGE = '\033[38;5;208m'
    FG_SYSTEMBLUE = '\033[38;5;12m'  # darker
    FG_DODGERBLUE2 = '\033[38;5;27m'  # lighter
    FG_PURPLE = '\033[38;5;93m'
    FG_DARKVIOLET = '\033[38;5;128m'
    FG_MAGENTA3 = '\033[38;5;164m'
    FG_GOLD3 = '\033[38;5;178m'
    FG_YELLOW1 = '\033[38;5;226m'
    FG_SKYBLUE1 = '\033[38;5;117m'
    FG_SKYBLUE2 = '\033[38;5;111m'
    FG_ROYALBLUE1 = '\033[38;5;63m'
    FG_CORNFLOWERBLUE = '\033[38;5;69m'
    FG_HOTPINK = '\033[38;5;206m'
    FG_DEEPPINK4 = '\033[38;5;89m'
    FG_MAGENTA3 = '\033[38;5;164m'
    FG_SALMON = '\033[38;5;209m'
    FG_MEDIUMORCHID1 = '\033[38;5;207m'
    FG_NAVAJOWHITE3 = '\033[38;5;144m'
    FG_DARKGOLDENROD = '\033[38;5;136m'
    FG_STEELBLUE1 = '\033[38;5;81m'
    FG_GREY42 = '\033[38;5;242m'
    FG_INDIANRED = '\033[38;5;131m'
    FG_DEEPSKYBLUE1 = '\033[38;5;39m'
    FG_ORANGE3 = '\033[38;5;172m'
    FG_RED3 = '\033[38;5;124m'
    FG_SEAGREEN2 = '\033[38;5;83m'
    FG_YELLOW3 = '\033[38;5;184m'
    FG_CYAN3 = '\033[38;5;43m'
    FG_CHARTREUSE3 = '\033[38;5;70m'
    FG_ORANGERED1 = '\033[38;5;202m'


# ----------------------------
def colorize(in_string, color_list='None'):
    return Colors.apply(in_string, color_list)


# ----------------------------
def colorize_prompt(prompt_str):
    # (P)revious, (N)ext, (G)oto, (D)etail, (H)ow, (W)hy, (E)xport, (Q)uit
    for str1 in 'PNGDHWEQCFSO':
        prompt_str = prompt_str.replace(f"({str1})", f"({Colors.apply(str1, 'bold')})")
    return prompt_str


# ---------------------------
def colorize_attr(attr_str, attr_color='attr_color'):
    if ':' in attr_str:
        attr_name = attr_str[0:attr_str.find(':') + 1]
        attr_value = attr_str[attr_str.find(':') + 1:].strip()
        return colorize(attr_name, attr_color) + ' ' + attr_value
    return colorize(attr_str, attr_color)


# ---------------------------
def colorize_dsrc(dsrc_str):
    if ':' in dsrc_str:
        return colorize_attr(dsrc_str, 'dsrc_color')
    return colorize(dsrc_str, 'dsrc_color')


# ---------------------------
def colorize_dsrc1(dsrc_str):
    return colorize(dsrc_str, 'dsrc_color')


# ---------------------------
def colorize_entity(entity_str, added_color=None):
    entity_color = 'entity_color' + (',' + added_color if added_color else '')
    if ':' in str(entity_str):
        return colorize_attr(entity_str, entity_color)
    return colorize(entity_str, entity_color)


# ---------------------------
def colorize_match_data(matchDict):
    if not matchDict['matchKey']:
        matchStr = colorize('not found!', 'bg_red,fg_white')
    else:
        goodSegments = []
        badSegments = []
        priorKey = ''
        keyColor = 'fg_green'
        for key in re.split('(\+|\-)', matchDict['matchKey']):
            if key in ('+', ''):
                priorKey = '+'
            elif key == '-':
                priorKey = '-'
            elif priorKey == '-':
                badSegments.append(key)
            else:
                goodSegments.append(key)
        if goodSegments:
            matchStr = colorize('+'.join(goodSegments), 'good')
        else:
            matchStr = ''
        if badSegments:
            matchStr += colorize('-' + '-'.join(badSegments), 'bad')

    if matchDict.get('ruleCode'):
        matchStr += f"\n {colorize(matchDict['ruleCode'], 'dim')}"

    if 'entityId' in matchDict and 'entityName' in matchDict:
        matchStr += f"\n to {colorize_entity(matchDict['entityId'])} {matchDict['entityName']}"
    elif 'entityId' in matchDict:
        matchStr += f" to {colorize_entity(matchDict['entityId'])}"

    return matchStr


# --------------------------------------
def print_message(msg_text, msg_type_or_color = ''):
    if msg_type_or_color.upper() == 'ERROR':
        msg_color = 'FG_RED'
    elif msg_type_or_color.upper() == 'WARNING':
        msg_color = 'FG_YELLOW'
    elif msg_type_or_color.upper() == 'INFO':
        msg_color = 'FG_CYAN'
    elif msg_type_or_color.upper() == 'SUCCESS':
        msg_color = 'FG_GREEN'
    else:
        msg_color = msg_type_or_color
    print(f"\n{Colors.apply(msg_text, msg_color)}\n")


# ==============================
class Node(object):

    def __init__(self, node_id):
        self.node_id = node_id
        self.node_desc = node_id
        self.node_text = None
        self.children = []
        self.parents = []

    def add_child(self, obj):
        self.children.append(obj)

    def add_parent(self, obj):
        self.parents.append(obj)

    def render_tree(self, filter_str=None):
        tree = ''
        tree += (self.node_desc + '\n')
        if self.node_text:
            tree += (self.node_text + '\n')
        parents = [{'node': self, 'next_child': 0, 'prior_nodes': [self]}]
        while parents:
            if parents[-1]['next_child'] == len(parents[-1]['node'].children):
                parents.pop()
                continue

            next_node = parents[-1]['node'].children[parents[-1]['next_child']]
            parents[-1]['next_child'] += 1

            prefix = ''
            for i in range(len(parents)):
                if i < len(parents) - 1:  # prior level
                    prefix += ('    ' if parents[i]['next_child'] == len(parents[i]['node'].children) else '\u2502   ')
                else:
                    prefix += ('\u2514\u2500\u2500 ' if parents[i]['next_child'] == len(parents[i]['node'].children) else '\u251c\u2500\u2500 ')

            filter_str_in_desc = False
            node_desc = next_node.node_desc
            if node_desc and filter_str:
                if filter_str in node_desc:
                    node_desc = node_desc.replace(filter_str, colorize(filter_str, 'bg_red, fg_white'))
                    filter_str_in_desc = True

            for line in node_desc.split('\n'):
                tree += (prefix + line + '\n')
                if prefix[-4:] == '\u251c\u2500\u2500 ':
                    prefix = prefix[0:-4] + '\u2502   '
                elif prefix[-4:] == '\u2514\u2500\u2500 ':
                    prefix = prefix[0:-4] + '    '

            if next_node.node_text:
                node_text = next_node.node_text
                if filter_str:
                    if filter_str in node_text:
                        node_text = node_text.replace(filter_str, colorize(filter_str, 'bg_red, fg_white'))
                    elif not filter_str_in_desc:
                        node_text = ''
                for line in node_text.split('\n'):
                    tree += (prefix + line + '\n')

            if next_node not in parents[-1]['prior_nodes'] and next_node.children:
                # gather all prior level nodes so don't render twice
                prior_nodes = []
                for parent in parents:
                    prior_nodes += parent['node'].children

                parents.append({'node': next_node, 'next_child': 0, 'prior_nodes': prior_nodes})
        return tree


# ==============================
class G2CmdShell(cmd.Cmd):

    # ---------------------------
    def __init__(self):
        cmd.Cmd.__init__(self)
        readline.set_completer_delims(' ')
        self.usePrettyTable = True

        self.intro = '\nType help or ? to list commands.\n'
        self.prompt = prompt

        # store config dicts for fast lookup
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

        # set feature display sequence
        self.featureSequence = {}
        self.featureSequence[self.ambiguousFtypeID] = 1  # ambiguous is first
        featureSequence = 2
        # scored features second
        for cfgRecord in sorted(self.cfgData['G2_CONFIG']['CFG_CFCALL'], key=lambda k: k['FTYPE_ID']):
            if cfgRecord['FTYPE_ID'] not in self.featureSequence:
                self.featureSequence[cfgRecord['FTYPE_ID']] = featureSequence
                featureSequence += 1
        # then the rest
        for cfgRecord in sorted(self.cfgData['G2_CONFIG']['CFG_FTYPE'], key=lambda k: k['FTYPE_ID']):
            if cfgRecord['FTYPE_ID'] not in self.featureSequence:
                self.featureSequence[cfgRecord['FTYPE_ID']] = featureSequence
                featureSequence += 1

        # misc
        self.dsrc_record_sep = '~|~'
        self.__hidden_methods = ('do_shell')
        self.doDebug = False
        self.searchMatchLevels = {1: 'Match', 2: 'Possible Match', 3: 'Possibly Related', 4: 'Name Only'}
        self.relatedMatchLevels = {1: 'Ambiguous Match', 2: 'Possible Match', 3: 'Possibly Related', 4: 'Name Only', 11: 'Disclosed Relation'}
        self.validMatchLevelParameters = {'0': 'SINGLE_SAMPLE',
                                          '1': 'DUPLICATE_SAMPLE',
                                          '2': 'AMBIGUOUS_MATCH_SAMPLE',
                                          '3': 'POSSIBLE_MATCH_SAMPLE',
                                          '4': 'POSSIBLY_RELATED_SAMPLE',
                                          'S': 'SINGLE_SAMPLE',
                                          'D': 'DUPLICATE_SAMPLE',
                                          'M': 'DUPLICATE_SAMPLE',
                                          'A': 'AMBIGUOUS_MATCH_SAMPLE',
                                          'P': 'POSSIBLE_MATCH_SAMPLE',
                                          'R': 'POSSIBLY_RELATED_SAMPLE',
                                          'SINGLE': 'SINGLE_SAMPLE',
                                          'DUPLICATE': 'DUPLICATE_SAMPLE',
                                          'MATCH': 'DUPLICATE_SAMPLE',
                                          'AMBIGUOUS': 'AMBIGUOUS_MATCH_SAMPLE',
                                          'POSSIBLE': 'POSSIBLE_MATCH_SAMPLE',
                                          'POSSIBLY': 'POSSIBLY_RELATED_SAMPLE',
                                          'RELATED': 'POSSIBLY_RELATED_SAMPLE'}

        # get settings
        settingsFileName = '.' + os.path.basename(sys.argv[0].lower().replace('.py', '')) + '_settings'

        self.settingsFileName = os.path.join(os.path.expanduser("~"), settingsFileName)
        try:
            self.current_settings = json.load(open(self.settingsFileName))
        except:
            self.current_settings = {}

        # default last snapshot/audit file from parameters
        if args.snapshot_file_name:
            self.current_settings['snapshotFile'] = args.snapshot_file_name
        if args.audit_file_name:
            self.current_settings['auditFile'] = args.audit_file_name

        # load prior snapshot file
        if 'snapshotFile' in self.current_settings and os.path.exists(self.current_settings['snapshotFile']):
            self.do_load(self.current_settings['snapshotFile'])
        else:
            self.snapshotFile = None
            self.snapshotData = {}

        # load prior audit file
        if 'auditFile' in self.current_settings and os.path.exists(self.current_settings['auditFile']):
            self.do_load(self.current_settings['auditFile'])
        else:
            self.auditFile = None
            self.auditData = {}

        # default settings for data and cross sources summary reports
        self.configurable_settings_list = [
            {'setting': 'color_scheme', 'values': ['default', 'light', 'dark'], 'description': 'light works better on dark backgrounds and vice-versa'},
            {'setting': 'statistic_level', 'values': ['record', 'entity'], 'description': 'sets the statistical point of view of the data and crossSourceSummary reports'},
            {'setting': 'data_source_suppression', 'values': ['off', 'on'], 'description': 'restricts the data and crossSourceSummary reports to only applicable data sources'},
            {'setting': 'show_relations_on_get', 'values': ['on', 'off'], 'description': 'always display relationships if any with each get of an entity ... or not!'}
        ]
        for setting_data in self.configurable_settings_list:
            self.current_settings[setting_data['setting']] = self.current_settings.get(setting_data['setting'], setting_data['values'][0])

        # set the color scheme
        self.do_set(f"color_scheme {self.current_settings['color_scheme']}")

        self.lastSearchResult = []
        self.currentReviewList = None
        self.currentRenderString = None

        # history
        self.readlineAvail = True if 'readline' in sys.modules else False
        self.histDisable = hist_disable
        self.histCheck()

    # ---------------------------
    def get_names(self):
        '''hides functions from available list of Commands. Seperate help sections for some '''
        return [n for n in dir(self.__class__) if n not in self.__hidden_methods]

    # ---------------------------
    # Override function from cmd module to make command completion case insensitive
    def completenames(self, text, *ignored):
        dotext = 'do_' + text
        return [a[3:] for a in self.get_names() if a.lower().startswith(dotext.lower())]

    # ---------------------------
    def emptyline(self):
        return

    # ---------------------------
    def do_quit(self, arg):
        return True

    # ---------------------------
    def do_exit(self, arg):
        self.do_quit(self)
        return True

    # ---------------------------
    def cmdloop(self):
        while True:
            try:
                cmd.Cmd.cmdloop(self)
                break
            except KeyboardInterrupt:
                ans = input('\n\nAre you sure you want to exit?  ')
                if ans in ['y', 'Y', 'yes', 'YES']:
                    break
            except TypeError as ex:
                print_message(str(ex), 'error')
                type_, value_, traceback_ = sys.exc_info()
                for item in traceback.format_tb(traceback_):
                    print(item)

    # ---------------------------
    def postloop(self):
        try:
            with open(self.settingsFileName, 'w') as f:
                json.dump(self.current_settings, f)
        except:
            pass

    # ---------------------------
    def help_knowledgeCenter(self):
        print(f"\nSenzing Knowledge Center: {colorize('https://senzing.zendesk.com/hc/en-us', 'highlight2, underline')}\n")

    # ---------------------------
    def help_support(self):
        print(f"\nSenzing Support Request: {colorize('https://senzing.zendesk.com/hc/en-us/requests/new', 'highlight2, underline')}\n")

    # ---------------------------
    def histCheck(self):

        self.histFileName = None
        self.histFileError = None
        self.histAvail = False

        if not self.histDisable:

            if readline:
                tmpHist = '.' + os.path.basename(sys.argv[0].lower().replace('.py', '_history'))
                self.histFileName = os.path.join(os.path.expanduser('~'), tmpHist)

                # Try and open history in users home first for longevity
                try:
                    open(self.histFileName, 'a').close()
                except IOError as e:
                    self.histFileError = f'{e} - Couldn\'t use home, trying /tmp/...'

                # Can't use users home, try using /tmp/ for history useful at least in the session
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

    # ---------------------------
    def do_history(self, arg):

        if self.histAvail:
            print()
            for i in range(readline.get_current_history_length()):
                print(readline.get_history_item(i + 1))
            print()
        else:
            print_message("History isn\'t available in this session", 'warning')

    # ---------------------------
    def do_shell(self, line):
        '''\nRun OS shell commands: !<command>\n'''
        if line:
            output = os.popen(line).read()
            print(f"\n{output}\n")

    # ---------------------------
    def help_set(self):
        print(textwrap.dedent(f'''\

        {colorize('Syntax:', 'highlight2')}
            set <setting> <value>

        {colorize('settings:', 'highlight2')} '''))
        print(colorize(f"    {'setting':<23} {'[possible values]':<22} {'current':<13} {'description'}", 'dim'))
        for setting_data in self.configurable_settings_list:
            current_value = colorize(self.current_settings[setting_data['setting']], 'bold')
            print(f"    {setting_data['setting']:<23} {'[' + ', '.join(setting_data['values']) + ']':<22} {current_value:<22} {colorize(setting_data['description'], 'dim')}")
        print()

    # ---------------------------
    def do_set(self, arg):
        if not arg:
            self.help_set()
            return

        settings_dict = {}
        for setting_data in self.configurable_settings_list:
            settings_dict[setting_data['setting']] = setting_data['values']

        if settings_dict:
            arg_list = arg.split()
            if len(arg_list) != 2 or (arg_list[0] not in settings_dict) or (arg_list[1] not in settings_dict[arg_list[0]]):
                print_message('Invalid setting', 'error')
                return

        self.current_settings[arg_list[0]] = arg_list[1]
        if arg_list[0] == 'color_scheme':
            Colors.set_theme(arg_list[1])


    # ---------------------------
    def do_version(self, arg):
        print(f"\nSenzing api version is: {api_version['BUILD_VERSION']}\n")


    # ---------------------------
    def help_load(self):

        print(textwrap.dedent(f'''\

        {colorize('Syntax:', 'highlight2')}
            load <snapshotFile.json>  {colorize('loads a snapshot file for review', 'dim')}
            load <auditFile.json>     {colorize('loads an audit file for review', 'dim')}

        '''))

    # ---------------------------
    def do_load(self, arg):

        statpackFileName = arg
        if not os.path.exists(statpackFileName):
            print_message('File not found!', 'error')
            return

        try:
            jsonData = json.load(open(statpackFileName, encoding="utf-8"))
        except ValueError as err:
            print_message(err, 'error')
            return

        if 'SOURCE' in jsonData and jsonData['SOURCE'] in ('G2Snapshot'):  # 'pocSnapshot',
            self.current_settings['snapshotFile'] = statpackFileName
            self.snapshotFile = statpackFileName
            self.snapshotData = jsonData
            print_message(f"sucessfully loaded {statpackFileName}", 'info')
        elif 'SOURCE' in jsonData and jsonData['SOURCE'] in ('G2Audit'):  # 'pocAudit',
            self.current_settings['auditFile'] = statpackFileName
            self.auditFile = statpackFileName
            self.auditData = jsonData
            print_message(f"sucessfully loaded {statpackFileName}", 'info')
        else:
            print_message('Invalid G2Explorer statistics file', 'error')

    # ---------------------------
    def complete_load(self, text, line, begidx, endidx):
        before_arg = line.rfind(" ", 0, begidx)
        if before_arg == -1:
            return  # arg not found

        fixed = line[before_arg + 1:begidx]  # fixed portion of the arg
        arg = line[before_arg + 1:endidx]
        pattern = arg + '*'

        completions = []
        for path in glob.glob(pattern):
            path = _append_slash_if_dir(path)
            completions.append(path.replace(fixed, "", 1))
        return completions

    # ---------------------------
    def help_quickLook(self):
        print('\nDisplays current data source stats without a snapshot\n')

    # ---------------------------
    def do_quickLook(self, arg):
        try:
            g2_diagnostic_module = G2Diagnostic()
            if api_version_major > 2:
                g2_diagnostic_module.init('pyG2Diagnostic', iniParams, False)
            else:
                g2_diagnostic_module.initV2('pyG2Diagnostic', iniParams, False)
            response = bytearray()
            g2_diagnostic_module.getDataSourceCounts(response)
            response = response.decode() if response else ''
            g2_diagnostic_module.destroy()
        except G2Exception as err:
            print_message(err, 'error')
            return
        jsonResponse = json.loads(response)

        has_entity_type = False
        for row in jsonResponse:
            if row.get('ETYPE_CODE', 'GENERIC') != 'GENERIC':
                has_entity_type = True
                break

        tblTitle = 'Data source counts'
        tblColumns = []
        tblColumns.append({'name': 'id', 'width': 5, 'align': 'center'})
        tblColumns.append({'name': 'DataSource', 'width': 30, 'align': 'left'})
        if has_entity_type:
            tblColumns.append({'name': 'EntityType', 'width': 30, 'align': 'left'})
        tblColumns.append({'name': 'ActualRecordCount', 'width': 20, 'align': 'right'})
        tblColumns.append({'name': 'DistinctRecordCount', 'width': 20, 'align': 'right'})
        tblRows = []
        for row in jsonResponse:
            entityType = '' if row['ETYPE_CODE'] == 'GENERIC' or row['ETYPE_CODE'] == row['DSRC_CODE'] else row['ETYPE_CODE']
            tblRow = []
            tblRow.append(colorize(row['DSRC_ID'], 'row_title'))
            tblRow.append(colorize_dsrc(row['DSRC_CODE']))
            if has_entity_type:
                tblRow.append(colorize(entityType, 'dim'))
            tblRow.append("{:,}".format(row['DSRC_RECORD_COUNT']))
            tblRow.append("{:,}".format(row['OBS_ENT_COUNT']))
            tblRows.append(tblRow)
        self.renderTable(tblTitle, tblColumns, tblRows)

    # ---------------------------
    def move_pointer(self, reply, current_item, max_items):
        ''' moves the sample record pointer for all reports '''
        if reply.upper().startswith('P'):  # previous
            if current_item == 0:
                input('\nNo prior records, press enter to continue')
            else:
                return current_item - 1
        elif reply.upper().startswith('N'):  # next
            if current_item == max_items - 1:
                input('\nno more records, press enter to continue')
            else:
                return current_item + 1
        elif reply.upper().startswith('G'):  # goto
            reply = reply[1:]
            if not reply:
                reply = input('\nSample item number to go to? ')
                if reply:
                    removeFromHistory()
            if reply:
                if reply.isnumeric() and int(reply) > 0 and int(reply) <= max_items:
                    return int(reply) - 1
                else:
                    print_message('Invalid sample item number for this sample set!', 'warning')
        return current_item

    # ---------------------------
    def export_report_sample(self, reply, currentRecords, fileName):
        if 'TO ' in reply.upper():
            fileName = reply[reply.upper().find('TO') + 2:].strip()
        if fileName:
            self.do_export(','.join(currentRecords) + ' to ' + fileName)

    # ---------------------------
    def help_auditSummary(self):
        print(textwrap.dedent(f'''\

        Displays audit statistics and examples.

        {colorize('Syntax:', 'highlight2')}
            auditSummary                        {colorize('with no parameters displays the overall stats', 'dim')}
            auditSummary merge                  {colorize('shows a list of merge sub-categories', 'dim')}
            auditSummary merge 1                {colorize('shows examples of merges in sub-category 1', 'dim')}
            auditSummary split                  {colorize('shows a list of split sub-categories', 'dim')}
            auditSummary split 1                {colorize('shows examples of splits in sub-category 1', 'dim')}
            auditSummary save to <filename.csv> {colorize('saves the entire audit report to a csv file', 'dim')}

        '''))


    # ---------------------------
    def do_auditSummary(self, arg):

        if not self.auditData or 'AUDIT' not in self.auditData:
            print_message('Please load a json file created with G2Audit.py to use this command', 'warning')
        elif not self.auditData['ENTITY'].get('PRIOR_COUNT'):
            print_message('Prior version audit file detected.  Please review with the prior version or re-create for this one.', 'warning')
            return

        categoryColors = {}
        categoryColors['MERGE'] = 'good'
        categoryColors['SPLIT'] = 'bad'
        categoryColors['SPLIT+MERGE'] = 'fg_red,bg_green'
        categoryColors['unknown'] = 'bg_red,fg_white'

        # display the summary if no arguments
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
            row.append(colorize('Prior Count', 'highlight2'))
            row.append(fmtStatistic(self.auditData['ENTITY']['PRIOR_COUNT']) if 'ENTITY' in self.auditData else '0')
            row.append(fmtStatistic(self.auditData['CLUSTERS']['PRIOR_COUNT']))
            row.append(fmtStatistic(self.auditData['PAIRS']['PRIOR_COUNT']))
            row.append('')
            row.append(colorize('Same Positives', 'highlight2'))
            row.append(colorize(fmtStatistic(self.auditData['PAIRS']['SAME_POSITIVE']), None))
            tblRows.append(row)

            row = []
            row.append(colorize('Newer Count', 'highlight2'))
            row.append(fmtStatistic(self.auditData['ENTITY']['NEWER_COUNT']) if 'ENTITY' in self.auditData else '0')
            row.append(fmtStatistic(self.auditData['CLUSTERS']['NEWER_COUNT']))
            row.append(fmtStatistic(self.auditData['PAIRS']['NEWER_COUNT']))
            row.append('')
            row.append(colorize('New Positives', categoryColors['MERGE']))
            row.append(colorize(fmtStatistic(self.auditData['PAIRS']['NEW_POSITIVE']), None))
            tblRows.append(row)

            row = []
            row.append(colorize('Common Count', 'highlight2'))
            row.append(fmtStatistic(self.auditData['ENTITY']['COMMON_COUNT']) if 'ENTITY' in self.auditData else '0')
            row.append(fmtStatistic(self.auditData['CLUSTERS']['COMMON_COUNT']))
            row.append(fmtStatistic(self.auditData['PAIRS']['COMMON_COUNT']))
            row.append('')
            row.append(colorize('New Negatives', categoryColors['SPLIT']))
            row.append(colorize(fmtStatistic(self.auditData['PAIRS']['NEW_NEGATIVE']), None))
            tblRows.append(row)

            row = []
            row.append(auditCategories[0][0])
            row.append(auditCategories[0][1])
            row.append('')  # (colorize(self.auditData['CLUSTERS']['INCREASE'], 'good') if self.auditData['CLUSTERS']['INCREASE'] else '')
            row.append('')  # (colorize(self.auditData['PAIRS']['INCREASE'], 'good') if self.auditData['PAIRS']['INCREASE'] else '')
            row.append('')
            row.append(colorize('Precision', 'highlight2'))
            row.append(colorize(self.auditData['PAIRS']['PRECISION'], None))
            tblRows.append(row)

            row = []
            row.append(auditCategories[1][0])
            row.append(auditCategories[1][1])
            row.append('')  # (colorize(self.auditData['CLUSTERS']['DECREASE'], 'bad') if self.auditData['CLUSTERS']['DECREASE'] else '')
            row.append('')  # (colorize(self.auditData['PAIRS']['DECREASE'], 'bad') if self.auditData['PAIRS']['DECREASE'] else '')
            row.append('')
            row.append(colorize('Recall', 'highlight2'))
            row.append(colorize(self.auditData['PAIRS']['RECALL'], None))
            tblRows.append(row)

            row = []
            row.append(auditCategories[2][0])
            row.append(auditCategories[2][1])
            row.append('')  # (colorize(self.auditData['CLUSTERS']['SIMILAR'], 'highlight1') if self.auditData['CLUSTERS']['SIMILAR'] else '')
            row.append('')  # (colorize(self.auditData['PAIRS']['SIMILAR'], 'highlight1') if self.auditData['PAIRS']['SIMILAR'] else '')
            row.append('')
            row.append(colorize('F1 Score', 'highlight2'))
            row.append(colorize(self.auditData['PAIRS']['F1-SCORE'], None))
            tblRows.append(row)

            # add any extra categories (which will occur if there were missing records)
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

        # build complete report and save to a file
        elif arg.upper().startswith('SAVE'):

            fileName = arg[7:].strip()
            fileHeaders = ['category', 'sub_category', 'audit_id']
            fileRows = []
            rowCnt = 0
            for category in self.auditData['AUDIT']:
                for subCategory in self.auditData['AUDIT'][category]['SUB_CATEGORY']:
                    for sampleRecords in self.auditData['AUDIT'][category]['SUB_CATEGORY'][subCategory]['SAMPLE']:
                        tableColumns, tableData = self.showAuditSample(sampleRecords, None)  # 2nd parmater cuts out colorize for save to file
                        recordHeaders = []
                        for columnDict in tableColumns:
                            columnName = columnDict['name'].lower()
                            if columnName not in recordHeaders:
                                recordHeaders.append(columnName)
                            if columnName not in fileHeaders:
                                fileHeaders.append(columnName)
                        for recordData in tableData:
                            rowData = dict(zip(recordHeaders, recordData))
                            rowData['category'] = category
                            rowData['sub_category'] = subCategory
                            rowData['audit_id'] = sampleRecords[0]['audit_id']
                            fileRows.append(rowData)
                            rowCnt += 1
                            if rowCnt % 1000 == 0:
                                print(f"{rowCnt} records processed")

            with open(fileName, 'w', encoding='utf-8') as f:
                w = csv.DictWriter(f, fileHeaders, dialect=csv.excel, quoting=csv.QUOTE_ALL)
                w.writeheader()
                for rowData in fileRows:
                    w.writerow(rowData)
            print_message(f"{rowCnt} records written to {fileName}!", 'success')

        # display next level report
        else:
            argList = arg.upper().split()
            if argList[0] not in self.auditData['AUDIT']:
                print_message(f"{arg} not found, please choose a valid split or merge category", 'error')
                return

            category = argList[0]
            categoryColor = categoryColors[category] if category in categoryColors else categoryColors['unknown']

            # get top 10 sub categories
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

            # display sub-categories
            if len(argList) == 1:
                tblTitle = category + ' Categories'
                tblColumns = []
                tblColumns.append({'name': 'Index', 'width': 10, 'align': 'center'})
                tblColumns.append({'name': 'Category', 'width': 25, 'align': 'left'})
                tblColumns.append({'name': 'Sub-category', 'width': 75, 'align': 'left'})
                tblColumns.append({'name': 'Count', 'width': 25, 'align': 'right'})
                tblRows = []
                for subCategoryRow in subCategoryList:
                    tblRows.append([colorize(subCategoryRow['INDEX'], 'row_title'), colorize(category, categoryColor), subCategoryRow['NAME'], fmtStatistic(subCategoryRow['COUNT'])])
                self.renderTable(tblTitle, tblColumns, tblRows)

                return

            # find the detail records to display
            indexCategories = []
            if argList[1].isdigit():
                for subCategoryRow in subCategoryList:
                    if subCategoryRow['INDEX'] == int(argList[1]):
                        indexCategories = subCategoryRow['LIST']
                        break

            if not indexCategories:
                print_message(f"Invalid subcategory for {argList[0].lower()}", 'error')
                return

            # gather sample records
            sampleRecords = []
            for subCategory in self.auditData['AUDIT'][category]['SUB_CATEGORY']:
                if subCategory in indexCategories:
                    sampleRecords += self.auditData['AUDIT'][category]['SUB_CATEGORY'][subCategory]['SAMPLE']

            # display sample records
            currentSample = 0
            while True:
                currentRecords = list(set([x['newer_id'] for x in sampleRecords[currentSample]]))
                self.currentReviewList = f"Item {currentSample + 1} of {len(sampleRecords)} for {argList[0]} category {argList[1]} - {subCategoryRow['NAME']}"
                self.showAuditSample(sampleRecords[currentSample], categoryColors)
                if len(currentRecords) == 1:
                    reply = input(colorize_prompt('Select (P)revious, (N)ext, (G)oto, (H)ow, (W)hy, (E)xport, (Q)uit ... '))
                    special_actions = 'HWE'
                else:
                    reply = input(colorize_prompt('Select (P)revious, (N)ext, (G)oto, (W)hy, (E)xport, (Q)uit ... '))
                    special_actions = 'WE'
                if reply:
                    removeFromHistory()
                else:
                    reply = 'N'
                if reply.upper().startswith('Q'):  # quit
                    break
                elif reply.upper()[0] in 'PNG':  # previous, next, goto
                    currentSample = self.move_pointer(reply, currentSample, len(sampleRecords))
                elif reply.upper()[0] in special_actions:
                    if reply.upper().startswith('W2'):
                        self.do_why(','.join(currentRecords) + ' old')
                    elif reply.upper().startswith('W'):
                        self.do_why(','.join(currentRecords))
                    elif reply.upper().startswith('H'):
                        self.do_how(','.join(currentRecords))
                    elif reply.upper().startswith('E'):
                        self.export_report_sample(reply, currentRecords, f"auditSample-{sampleRecords[currentSample][0]['audit_id']}.json")
                    input('\npress enter to return to report')
            self.currentReviewList = None

    # ---------------------------
    def complete_auditSummary(self, text, line, begidx, endidx):
        before_arg = line.rfind(" ", 0, begidx)

        fixed = line[before_arg + 1:begidx]  # fixed portion of the arg
        arg = line[before_arg + 1:endidx]

        spaces = line.count(' ')
        if spaces <= 1:
            possibles = []
            if self.auditData:
                for category in self.auditData['AUDIT']:
                    possibles.append(category)
        else:
            possibles = []

        return [i for i in possibles if i.lower().startswith(arg.lower())]

    # ---------------------------
    def showAuditSample(self, arg, categoryColors=None):

        auditRecords = arg

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
        getFlagList.append('G2_ENTITY_INCLUDE_ALL_FEATURES')
        getFlagList.append('G2_ENTITY_INCLUDE_ENTITY_NAME')
        getFlagList.append('G2_ENTITY_INCLUDE_RECORD_DATA')
        getFlagList.append('G2_ENTITY_INCLUDE_RECORD_MATCHING_INFO')
        getFlagList.append('G2_ENTITY_INCLUDE_RECORD_FEATURE_IDS')

        # gather all the record data
        ftypesUsed = []
        recordList = []
        entityList = set([x['newer_id'] for x in auditRecords])
        for entityId in entityList:
            if entityId == 'unknown':  # bypass missing
                continue
            try:
                jsonData = execute_api_call('getEntityByEntityID', getFlagList, int(entityId))
            except Exception as err:
                print_message(err, 'error')
                return -1 if calledDirect else 0

            # get the list of features for the entity
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

            # get the list of features for each record
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

        # combine the features with the actual audit records
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

        # add the columns to the table format and do the final formatting
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
            row.append(colorize(auditRecord['data_source'], 'dsrc_color' if categoryColors else None) if 'data_source' in auditRecord else '')
            row.append(auditRecord['record_id'])
            row.append(auditRecord['prior_id'])
            row.append(auditRecord['prior_score'])
            row.append(colorize(str(auditRecord['newer_id']), 'entity_color' if categoryColors else None))
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

    # ---------------------------
    def help_entitySizeBreakdown(self):
        print(textwrap.dedent(f'''\

        Displays the number of entities by how many records they contain.

        {colorize('Syntax:', 'highlight2')}
            entitySizeBreakdown                    {colorize('with no parameters displays the overall stats', 'dim')}
            entitySizeBreakdown = 3                {colorize('use =, > or < # to select examples of entities of a certain size', 'dim')}
            entitySizeBreakdown > 10 review        {colorize('to just browse the review items of entities greater than size 10', 'dim')}
            entitySizeBreakdown = review name+addr {colorize('to just browse the name+addr review items of any size', 'dim')}

        {colorize('review items:', 'highlight2')}
            Review items are suggestions of records to look at because they contain multiple names, addresses, dobs, etc.
            They may be overmatches or they may just be large entities with lots of values.

        '''))
    # ---------------------------
    def do_entitySizeBreakdown(self, arg):

        if not self.snapshotData or (not self.snapshotData.get('ENTITY_SIZE_BREAKDOWN') and not self.snapshotData.get('TEMP_ESB_STATS')):
            print_message('Please load a json file created with G2Snapshot.py to access this report', 'warning')
            return

        if not self.snapshotData.get('ENTITY_SIZE_BREAKDOWN'):
            self.compute_entitySizeBreakdown()

        # display the summary if no arguments
        if not arg:
            tblTitle = 'Entity Size Breakdown from %s' % self.snapshotFile
            tblColumns = []
            tblColumns.append({'name': 'Entity Size', 'width': 10, 'align': 'center'})
            tblColumns.append({'name': 'Entity Count', 'width': 10, 'align': 'center'})
            tblColumns.append({'name': 'Review Count', 'width': 10, 'align': 'center'})
            tblColumns.append({'name': 'Review Features', 'width': 75, 'align': 'left'})

            tblRows = []
            for entitySizeData in sorted(self.snapshotData['ENTITY_SIZE_BREAKDOWN'], key=lambda k: k['ENTITY_SIZE'], reverse=True):
                row = []
                row.append(colorize(entitySizeData['ENTITY_SIZE_GROUP'], 'row_title'))
                row.append(entitySizeData['ENTITY_COUNT'])
                row.append(entitySizeData['REVIEW_COUNT'])
                row.append(' | '.join(colorize(x, 'caution') for x in sorted(entitySizeData['REVIEW_FEATURES'])))
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

                # add these entities if they satisfy the entity size argument
                if sign in ('=', '>=', '<=') and entitySizeData['ENTITY_SIZE'] == size:
                    theseRecords = entitySizeData['SAMPLE_ENTITIES']
                elif sign in ('<', '<=') and entitySizeData['ENTITY_SIZE'] < size:
                    theseRecords = entitySizeData['SAMPLE_ENTITIES']
                elif sign in ('>', '>=') and entitySizeData['ENTITY_SIZE'] > size:
                    theseRecords = entitySizeData['SAMPLE_ENTITIES']
                else:
                    continue

                # filter for review features
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
                print_message('No records found', 'warning')
            else:

                currentSample = 0
                while True:
                    self.currentReviewList = f"Item {currentSample + 1} of {len(sampleRecords)} for Entity Size {sampleRecords[currentSample]['ENTITY_SIZE']}"
                    if 'REVIEW_FEATURES' in sampleRecords[currentSample]:
                        reviewItems = []
                        for ftypeCode in sampleRecords[currentSample]['REVIEW_FEATURES']:
                            reviewItems.append(f"{ftypeCode} ({sampleRecords[currentSample][ftypeCode]})")
                        self.currentReviewList += ', review for: ' + ', '.join(reviewItems)

                    currentRecords = [str(sampleRecords[currentSample]['ENTITY_ID'])]
                    returnCode = self.do_get(currentRecords[0])
                    if returnCode != 0:
                        print_message('This entity no longer exists', 'error')

                    reply = input(colorize_prompt('Select (P)revious, (N)ext, (G)oto, (D)etail, (H)ow, (W)hy, (E)xport, (Q)uit ...'))
                    if reply:
                        removeFromHistory()
                    else:
                        reply = 'N'

                    if reply.upper().startswith('Q'):  # quit
                        break
                    elif reply.upper()[0] in 'PNG':  # previous, next, goto
                        currentSample = self.move_pointer(reply, currentSample, len(sampleRecords))
                    elif reply.upper()[0] in 'DHWE':
                        if reply.upper().startswith('D'):
                            self.do_get('detail ' + ','.join(currentRecords))
                        elif reply.upper().startswith('W'):
                            self.do_why(','.join(currentRecords))
                        elif reply.upper().startswith('H'):
                            self.do_how(','.join(currentRecords))
                        elif reply.upper().startswith('E'):
                            self.export_report_sample(reply, currentRecords, f"{'-'.join(currentRecords)}.json")
                        input('\npress enter to return to report')
                self.currentReviewList = None

    # ---------------------------
    def compute_entitySizeBreakdown(self):
        esb_data = {}
        for str_entitySize in sorted(self.snapshotData['TEMP_ESB_STATS'].keys()):
            entitySize = int(str_entitySize)
            if entitySize <= 3:  # super small
                maxExclusiveCnt = 1
                maxNameCnt = 2
                maxAddrCnt = 2
            elif entitySize <= 10:  # small
                maxExclusiveCnt = 1
                maxNameCnt = 3
                maxAddrCnt = 3
            elif entitySize <= 50:  # medium
                maxExclusiveCnt = 1
                maxNameCnt = 10
                maxAddrCnt = 10
            else:  # large
                maxExclusiveCnt = 1  # large
                maxNameCnt = 25
                maxAddrCnt = 25

            # setup for the entity size
            if entitySize < 10:
                entitySizeLevel = entitySize
            elif entitySize < 100:
                entitySizeLevel = int(entitySize / 10) * 10
            else:
                entitySizeLevel = int(entitySize / 100) * 100
            if entitySizeLevel not in esb_data:
                esb_data[entitySizeLevel] = {'ENTITY_COUNT': 0,
                                             'SAMPLE_ENTITIES': [],
                                             'REVIEW_COUNT': 0,
                                             'REVIEW_FEATURES': []}
            esb_data[entitySizeLevel]['ENTITY_COUNT'] += self.snapshotData['TEMP_ESB_STATS'][str_entitySize]['COUNT']

            # review each entity
            for sample_record in self.snapshotData['TEMP_ESB_STATS'][str_entitySize]['SAMPLE']:
                review_features = []
                for raw_attr in sample_record.keys():
                    if raw_attr in ('ENTITY_ID', 'ENTITY_SIZE'):
                        continue
                    ftype_code = raw_attr
                    ftype_excl = self.ftypeCodeLookup[ftype_code]['FTYPE_EXCL']
                    distinctFeatureCount = sample_record[ftype_code]
                    if ftype_code == 'NAME' and distinctFeatureCount > maxNameCnt:
                        review_features.append(ftype_code)
                    elif ftype_code == 'ADDRESS' and distinctFeatureCount > maxAddrCnt:
                        review_features.append(ftype_code)
                    elif ftype_excl == 'Yes' and distinctFeatureCount > maxExclusiveCnt:
                        review_features.append(ftype_code)
                if review_features:
                    sample_record['REVIEW_FEATURES'] = review_features
                    esb_data[entitySizeLevel]['REVIEW_FEATURES'] = list(set(esb_data[entitySizeLevel]['REVIEW_FEATURES'] + review_features))
                    esb_data[entitySizeLevel]['REVIEW_COUNT'] += 1
                esb_data[entitySizeLevel]['SAMPLE_ENTITIES'].append(sample_record)

        self.snapshotData['ENTITY_SIZE_BREAKDOWN'] = []
        for entitySizeLevel in sorted(esb_data.keys()):
            entitySizeRecord = esb_data[entitySizeLevel]
            entitySizeRecord['ENTITY_SIZE'] = entitySizeLevel
            entitySizeRecord['ENTITY_SIZE_GROUP'] = str(entitySizeLevel) + ('+' if int(entitySizeLevel) >= 10 else '')
            self.snapshotData['ENTITY_SIZE_BREAKDOWN'].append(entitySizeRecord)

        try:
            with open(self.snapshotFile, 'w') as f:
                json.dump(self.snapshotData, f)
        except IOError as err:
            print_message(f"Could not save review to {self.snapshotFile}", 'error')

    # ---------------------------
    def help_dataSourceSummary(self):
        print(textwrap.dedent(f'''\

        Displays the statistics for the different match levels within each data source.

        {colorize('Syntax:', 'highlight2')}
            dataSourceSummary                               {colorize('with no parameters displays the overall stats', 'dim')}
            dataSourceSummary <dataSourceCode> <matchLevel> {colorize('where 0=Singletons, 1=Duplicates, 2=Ambiguous, 3=Possibles, 4=Relationships', 'dim')}
        '''))


    # ---------------------------
    def do_dataSourceSummary(self, arg):
        if not self.snapshotData or 'DATA_SOURCES' not in self.snapshotData:
            print_message('Please load a json file created with G2Snapshot.py to use this command', 'warning')
            return

        # display the summary if no arguments
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
                row.append(colorize_dsrc(dataSource))
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
                print_message('Arguments missing: data source and match level are required', 'warning')
                return

            dataSource = argTokens[0].upper()
            if dataSource not in self.snapshotData['DATA_SOURCES']:
                print_message('Invalid data source', 'error')
                return

            matchLevel = argTokens[1].upper()
            matchLevelCode = None
            for matchLevelParameter in self.validMatchLevelParameters:
                if matchLevel.startswith(matchLevelParameter):
                    matchLevelCode = self.validMatchLevelParameters[matchLevelParameter]
                    break
            if not matchLevelCode:
                print_message('Invalid match level', 'error')
                return

            try:
                sampleRecords = [k for k in self.snapshotData['DATA_SOURCES'][dataSource][matchLevelCode]]
            except:
                sampleRecords = []
            if len(sampleRecords) == 0:
                print_message('No records found', 'warning')
                return

            currentSample = 0
            while True:
                self.currentReviewList = f"Sample {currentSample + 1} of {len(sampleRecords)} for {matchLevelCode} in {dataSource}"

                if matchLevelCode in ('SINGLE_SAMPLE', 'DUPLICATE_SAMPLE'):
                    currentRecords = [str(sampleRecords[currentSample])]
                    returnCode = self.do_get(currentRecords[0], dataSourceFilter=[dataSource])
                else:
                    currentRecords = sampleRecords[currentSample].split()[:2]
                    if matchLevelCode == 'AMBIGUOUS_MATCH_SAMPLE':
                        ambiguousList = self.getAmbiguousEntitySet(currentRecords[0])  # is this the ambiguous entity
                        if ambiguousList:
                            currentRecords = ambiguousList
                        else:
                            ambiguousList = self.getAmbiguousEntitySet(currentRecords[1])  # or is this the ambiguous entity
                            if ambiguousList:
                                currentRecords = ambiguousList
                            else:
                                pass  # if its neither, just show the original two entities
                    returnCode = self.do_compare(','.join(currentRecords), dataSourceFilter=[dataSource])

                if returnCode != 0:
                    print_message('This entity no longer exists', 'error')

                if matchLevelCode in ('SINGLE_SAMPLE', 'DUPLICATE_SAMPLE'):
                    reply = input(colorize_prompt('Select (P)revious, (N)ext, (G)oto, (D)etail, (H)ow, (W)hy, (E)xport, (Q)uit ...'))
                    special_actions = 'DHWE'
                else:
                    reply = input(colorize_prompt('Select (P)revious, (N)ext, (G)oto, (W)hy, (E)xport, (Q)uit ...'))
                    special_actions = 'WE'
                if reply:
                    removeFromHistory()
                else:
                    reply = 'N'

                if reply.upper().startswith('Q'):  # quit
                    break
                elif reply.upper()[0] in 'PNG':  # previous, next, goto
                    currentSample = self.move_pointer(reply, currentSample, len(sampleRecords))
                elif reply.upper()[0] in special_actions:
                    if reply.upper().startswith('D'):
                        self.do_get('detail ' + ','.join(currentRecords))
                    elif reply.upper().startswith('W'):
                        self.do_why(','.join(currentRecords))
                    elif reply.upper().startswith('H'):
                        self.do_how(','.join(currentRecords))
                    elif reply.upper().startswith('E'):
                        self.export_report_sample(reply, currentRecords, f"{'-'.join(currentRecords)}.json")
                    input('\npress enter to return to report')
            self.currentReviewList = None

    # ---------------------------
    def complete_dataSourceSummary(self, text, line, begidx, endidx):
        before_arg = line.rfind(" ", 0, begidx)
        # if before_arg == -1:
        #    return # arg not found

        fixed = line[before_arg + 1:begidx]  # fixed portion of the arg
        arg = line[before_arg + 1:endidx]

        spaces = line.count(' ')
        if spaces <= 1:
            possibles = []
            if self.snapshotData:
                for dataSource in sorted(self.snapshotData['DATA_SOURCES']):
                    possibles.append(dataSource)
        elif spaces == 2:
            possibles = ['singles', 'duplicates', 'matches', 'ambiguous', 'possibles', 'relationships']
        else:
            possibles = []

        return [i for i in possibles if i.lower().startswith(arg.lower())]

    # ---------------------------
    def help_crossSourceSummary(self):
        print(textwrap.dedent(f'''\

        Displays the statistics for the different match levels across data sources.

        {colorize('Syntax:', 'highlight2')}
            crossSourceSummary                                           {colorize('with no parameters displays the overall stats', 'dim')}
            crossSourceSummary <dataSource1>                             {colorize('displays the cross matches for that data source only', 'dim')}
            crossSourceSummary <dataSource1> <dataSource2> <matchLevel>  {colorize('where 1=Matches, 2=Ambiguous, 3=Possibles, 4=Relationships', 'dim')}
        '''))


    # ---------------------------
    def do_crossSourceSummary(self, arg):

        if not self.snapshotData or 'DATA_SOURCES' not in self.snapshotData:
            print_message('Please load a json file created with G2Snapshot.py to use this command', 'warning')
            return

        # display the summary if no arguments
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
                    row = []
                    row.append(colorize_dsrc(dataSource1))
                    row.append(colorize_dsrc(dataSource2))

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
                print_message('Arguments missing: two data sources and match level are required', 'warning')
                return

            dataSource1 = argTokens[0].upper()
            if dataSource1 not in self.snapshotData['DATA_SOURCES']:
                print_message(f"Invalid data source: {dataSource1}", 'error')
                return

            dataSource2 = argTokens[1].upper()
            if dataSource2 not in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES']:
                print_message(f"Invalid data source: {dataSource2}", 'error')
                return

            matchLevel = argTokens[2].upper()
            matchLevelCode = None
            for matchLevelParameter in self.validMatchLevelParameters:
                if matchLevel.startswith(matchLevelParameter):
                    matchLevelCode = self.validMatchLevelParameters[matchLevelParameter]
                    break

            if not matchLevelCode:
                print_message('Invalid match level', 'error')
                return

            # duplicates are matches for cross source
            if matchLevelCode == 'DUPLICATE_SAMPLE':
                matchLevelCode = 'MATCH_SAMPLE'

            try:
                sampleRecords = [k for k in self.snapshotData['DATA_SOURCES'][dataSource1]['CROSS_MATCHES'][dataSource2][matchLevelCode]]
            except:
                sampleRecords = []

            if len(sampleRecords) == 0:
                print_message('No records found', 'warning')
                return

            currentSample = 0
            while True:
                self.currentReviewList = f"Sample {currentSample + 1} of {len(sampleRecords)} for {matchLevelCode} between {dataSource1} and {dataSource2}"

                if matchLevelCode in ('MATCH_SAMPLE'):
                    currentRecords = [str(sampleRecords[currentSample])]
                    returnCode = self.do_get(currentRecords[0], dataSourceFilter=[dataSource1, dataSource2])
                else:
                    currentRecords = sampleRecords[currentSample].split()[:2]
                    if matchLevelCode == 'AMBIGUOUS_MATCH_SAMPLE':
                        ambiguousList = self.getAmbiguousEntitySet(currentRecords[0])  # is this the ambiguous entity
                        if ambiguousList:
                            currentRecords = ambiguousList
                        else:
                            ambiguousList = self.getAmbiguousEntitySet(currentRecords[1])  # or is this the ambiguous entity
                            if ambiguousList:
                                currentRecords = ambiguousList
                            else:
                                pass  # if its neither, just show the original two entities
                    returnCode = self.do_compare(','.join(currentRecords), dataSourceFilter=[dataSource1, dataSource2])

                if returnCode != 0:
                    print_message('This entity no longer exists', 'error')

                if matchLevelCode in ('MATCH_SAMPLE'):
                    reply = input(colorize_prompt('Select (P)revious, (N)ext, (G)oto, (D)etail, (H)ow, (W)hy, (E)xport, (Q)uit ...'))
                    special_actions = 'DHWE'
                else:
                    reply = input(colorize_prompt('Select (P)revious, (N)ext, (G)oto, (W)hy, (E)xport, (Q)uit ...'))
                    special_actions = 'WE'
                if reply:
                    removeFromHistory()
                else:
                    reply = 'N'

                if reply.upper().startswith('Q'):  # quit
                    break
                elif reply.upper()[0] in 'PNG':  # previous, next, goto
                    currentSample = self.move_pointer(reply, currentSample, len(sampleRecords))
                elif reply.upper()[0] in special_actions:
                    if reply.upper().startswith('D'):
                        self.do_get('detail ' + ','.join(currentRecords))
                    elif reply.upper().startswith('W'):
                        self.do_why(','.join(currentRecords))
                    elif reply.upper().startswith('H'):
                        self.do_how(','.join(currentRecords))
                    elif reply.upper().startswith('E'):
                        self.export_report_sample(reply, currentRecords, f"{'-'.join(currentRecords)}.json")
                    input('\npress enter to return to report')
            self.currentReviewList = None

    # ---------------------------
    def complete_crossSourceSummary(self, text, line, begidx, endidx):
        before_arg = line.rfind(" ", 0, begidx)
        if before_arg == -1:
            return  # arg not found

        fixed = line[before_arg + 1:begidx]  # fixed portion of the arg
        arg = line[before_arg + 1:endidx]

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
            possibles = ['singles', 'duplicates', 'matches', 'ambiguous', 'possibles', 'relationships']
        else:
            possibles = []

        return [i for i in possibles if i.lower().startswith(arg.lower())]

    # ---------------------------
    def help_search(self):
        print(textwrap.dedent(f'''\

        Search for an entity by its attributes.

        {colorize('Syntax:', 'highlight2')}
            search Joe Smith {colorize('without a json structure performs a search on name alone', 'dim')}
            search {'{'}"name_full": "Joe Smith"{'}'}
            search {'{'}"name_org": "ABC Company"{'}'}
            search {'{'}"name_last": "Smith", "name_first": "Joe", "date_of_birth": "1992-12-10"{'}'}
            search {'{'}"name_org": "ABC Company", "addr_full": "111 First St, Anytown, USA 11111"{'}'}

        {colorize('Notes:', 'highlight2')}
            Searching by name alone may not locate a specific entity.
            Try adding a date of birth, address, or phone number if not found by name alone.
        '''))


    # ---------------------------
    def do_search(self, arg):
        if not arg:
            self.help_search()
            return

        try:
            parmData = dictKeysUpper(json.loads(arg)) if arg.startswith('{') else {"PERSON_NAME_FULL": arg, "ORGANIZATION_NAME_ORG": arg}
        except (ValueError, KeyError) as err:
            print_message(f"Invalid json parameter: {err}", 'error')
            return

        print('\nSearching ...')
        searchJson = parmData
        searchFlagList = ['G2_SEARCH_INCLUDE_ALL_ENTITIES',
                          'G2_SEARCH_INCLUDE_FEATURE_SCORES',
                          'G2_ENTITY_INCLUDE_ENTITY_NAME',
                          'G2_ENTITY_INCLUDE_RECORD_DATA',
                          'G2_SEARCH_INCLUDE_STATS',
                          'G2_ENTITY_INCLUDE_ALL_RELATIONS',
                          'G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO']
        try:
            jsonResponse = execute_api_call('searchByAttributes', searchFlagList, json.dumps(searchJson))
        except Exception as err:
            print_message(err, 'error')
            return

        # constants for descriptions and sort orders
        dataSourceOrder = []  # place your data sources here!

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

            # create a list of data sources we found them in
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
                    dataSourceList.append(colorize_dsrc(dataSource + ': ' + dataSources[dataSource][0]))
                else:
                    dataSourceList.append(colorize_dsrc(dataSource + ': ' + str(len(dataSources[dataSource])) + ' records'))

            disclosedCount = 0
            derivedCount = 0
            for relationship in resolvedEntityBase['ENTITY']['RELATED_ENTITIES'] if 'RELATED_ENTITIES' in resolvedEntityBase['ENTITY'] else []:
                if relationship['IS_DISCLOSED'] > 0:
                    disclosedCount += 1
                else:
                    derivedCount += 1
            relationshipLines = []
            if derivedCount > 0:
                relationshipLines.append(f"{derivedCount} {colorize('(derived)', 'dim')}")
            if disclosedCount > 0:
                relationshipLines.append(f"{disclosedCount} {colorize('(disclosed)', 'dim')}")

            # determine the matching criteria
            matchLevel = self.searchMatchLevels[resolvedEntityMatchInfo['MATCH_LEVEL']]
            matchKey = resolvedEntityMatchInfo['MATCH_KEY']
            ruleCode = resolvedEntityMatchInfo['ERRULE_CODE']
            # scoring
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
                    matchingScore = scoreRecord[scoreCode]
                    matchingValue = scoreRecord['CANDIDATE_FEAT']
                    if featureCode not in bestScores:
                        bestScores[featureCode] = {}
                        bestScores[featureCode]['score'] = 0
                        bestScores[featureCode]['value'] = 'n/a'
                    if matchingScore > bestScores[featureCode]['score']:
                        bestScores[featureCode]['score'] = matchingScore
                        bestScores[featureCode]['value'] = matchingValue

            # perform scoring (use stored match_score if not overridden in the mapping document)
            matchedScore = bestScores['NAME']['score']
            matchedName = bestScores['NAME']['value']

            weightedScores = {}
            for featureCode in bestScores:
                weightedScores[featureCode] = {}
                weightedScores[featureCode]['threshold'] = 0
                weightedScores[featureCode]['+weight'] = 100
                weightedScores[featureCode]['-weight'] = 0
                # if scoredFeatureCount > 1:

            matchScore = 0
            for featureCode in bestScores:
                if featureCode in weightedScores:
                    if bestScores[featureCode]['score'] >= weightedScores[featureCode]['threshold']:
                        matchScore += int(round(bestScores[featureCode]['score'] * (weightedScores[featureCode]['+weight'] / 100), 0))
                    elif '-weight' in weightedScores[featureCode]:
                        matchScore += -weightedScores[featureCode]['-weight']  # actual score does not matter if below the threshold

            # create the possible match entity one-line summary
            row = []
            row.append(str(searchIndex))  # note this gets re-ordered below
            row.append(str(resolvedEntity['ENTITY_ID']))
            row.append(resolvedEntity['ENTITY_NAME'] + (('\n' + ' aka: ' + matchedName) if matchedName and matchedName != resolvedEntity['ENTITY_NAME'] else ''))
            row.append('\n'.join(dataSourceList))
            matchData = {}
            matchData['matchKey'] = matchKey
            matchData['ruleCode'] = self.getRuleDesc(ruleCode)
            row.append(colorize_match_data(matchData))
            row.append(matchScore)
            row.append('\n'.join(relationshipLines))
            matchList.append(row)

        if len(matchList) == 0:
            if 'SEARCH_STATISTICS' in jsonResponse:
                if jsonResponse['SEARCH_STATISTICS'][0]['CANDIDATE_KEYS']['SUMMARY']['FOUND'] > 0:
                    msg = '\tOne or more entities were found but did not score high enough to be returned'
                    msg += '\n\tPlease include additional or more complete attributes in your search'
                elif jsonResponse['SEARCH_STATISTICS'][0]['CANDIDATE_KEYS']['SUMMARY']['GENERIC'] > 0:
                    msg = '\tToo many entities would be returned'
                    msg += '\n\tPlease include additional attributes to narrow the search results'
                elif jsonResponse['SEARCH_STATISTICS'][0]['CANDIDATE_KEYS']['SUMMARY']['NOT_FOUND'] > 0:
                    msg = '\tNo entities at all were found'
                    msg += '\n\tPlease search by other attributes for this entity if you feel it should exist'
                else:
                    msg = '\tNo search keys were even generated'
                    msg += '\n\tPlease search by other attributes'

            else:  # older versions do not have statistics
                msg = '\tNo matches found or there were simply too many to return'
                msg += '\n\tPlease include additional search parameters if you feel this entity is in the database'
            print_message(msg, 'warning')

        else:

            # sort the list by match score descending
            matchList = sorted(matchList, key=lambda x: x[5], reverse=True)

            # store the last search result and colorize
            self.lastSearchResult = []
            for i in range(len(matchList)):
                self.lastSearchResult.append(matchList[i][1])
                matchList[i][0] = colorize(i + 1, 'row_title')
                matchList[i][1] = colorize_entity(matchList[i][1])
                matchList[i][2] = matchList[i][2]
            self.renderTable(tblTitle, tblColumns, matchList)

        print('')

    # ---------------------------
    def help_get(self):
        print(textwrap.dedent(f'''\

        Displays a particular entity by entity_id or by data_source and record_id.

        {colorize('Syntax:', 'highlight2')}
            get <entity_id>               {colorize("looks up an entity's resume by entity ID", 'dim')}
            get <dataSource> <recordID>   {colorize("looks up an entity's resume by data source and record ID", 'dim')}
            get search <search index>     {colorize("looks up an entity's resume by search index (requires a prior search)", 'dim')}
            get detail <entity_id>        {colorize('adding the "detail" tag displays each record rather than a summary by data source', 'dim')}
            get features <entity_id>      {colorize('adding the "features" tag displays the entity features rather than the resume', 'dim')}

        '''))


    # ---------------------------
    def do_get(self, arg, **kwargs):
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'
        if not arg:
            self.help_get()
            return -1 if calledDirect else 0

        # get possible data source list
        if 'dataSourceFilter' in kwargs and self.current_settings['data_source_suppression'] == 'on':
            dataSourceFilter = kwargs['dataSourceFilter']
        else:
            dataSourceFilter = None

        if 'DETAIL ' in arg.upper():
            showDetail = True
            arg = arg.upper().replace('DETAIL ', '')
        else:
            showDetail = False

        if 'FEATURES ' in arg.upper():
            showFeatures = True
            arg = arg.upper().replace('FEATURES ', '')
        else:
            showFeatures = False

        if len(arg.split()) == 2 and arg.split()[0].upper() == 'SEARCH':
            lastToken = arg.split()[1]
            if not lastToken.isdigit() or lastToken == '0' or int(lastToken) > len(self.lastSearchResult):
                print_message('Invalid search index from the prior search', 'error')
                return -1 if calledDirect else 0
            else:
                arg = str(self.lastSearchResult[int(lastToken) - 1])

        argList = arg.split()
        if len(argList) not in (1, 2):
            print_message('Incorrect number of parameters', 'warning')
            return -1 if calledDirect else 0

        if len(argList) == 1 and not argList[0].isnumeric():
            print_message('Entity ID must be numeric', 'error')
            return -1 if calledDirect else 0


        getFlagList = ['G2_ENTITY_INCLUDE_ENTITY_NAME',
                       'G2_ENTITY_INCLUDE_RECORD_DATA',
                       'G2_ENTITY_INCLUDE_RECORD_MATCHING_INFO',
                       'G2_ENTITY_INCLUDE_RECORD_FORMATTED_DATA',
                       'G2_ENTITY_INCLUDE_ALL_RELATIONS',
                       'G2_ENTITY_INCLUDE_RELATED_ENTITY_NAME',
                       'G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO',
                       'G2_ENTITY_INCLUDE_RELATED_RECORD_SUMMARY']
        try:
            if len(argList) == 1:
                resolvedJson = execute_api_call('getEntityByEntityID', getFlagList, int(argList[0]))
            else:
                resolvedJson = execute_api_call('getEntityByRecordID', getFlagList, argList)
        except Exception as err:
            print_message(err, 'error')
            return -1 if calledDirect else 0

        relatedEntityCount = len(resolvedJson['RELATED_ENTITIES']) if 'RELATED_ENTITIES' in resolvedJson else 0
        entityID = str(resolvedJson['RESOLVED_ENTITY']['ENTITY_ID'])
        entityName = resolvedJson['RESOLVED_ENTITY']['ENTITY_NAME']

        if showFeatures:
            tblColumns = []
            tblColumns.append({'name': 'Feature', 'width': 30, 'align': 'left'})
            tblColumns.append({'name': 'Description', 'width': 50, 'align': 'left'})
            tblColumns.append({'name': 'Elements', 'width': 100, 'align': 'left'})
            reportType = 'features'
            tblTitle = f"Entity {reportType} for entity {colorize_entity(entityID)}: {entityName}"
            tblRows = self.getFeatures(entityID)
            if tblRows:
                self.renderTable(tblTitle, tblColumns, tblRows)
            return 0
        else:
            tblColumns = []
            tblColumns.append({'name': 'Record ID', 'width': 50, 'align': 'left'})
            tblColumns.append({'name': 'Entity Data', 'width': 100, 'align': 'left'})
            tblColumns.append({'name': 'Additional Data', 'width': 100, 'align': 'left'})
            reportType = 'detail' if showDetail else 'summary'
            tblTitle = f"Entity {reportType} for entity {colorize_entity(entityID)}: {entityName}"
            if webapp_url:
                tblTitle += f"  {colorize('WebApp:', 'dim')} " + colorize(f"{webapp_url}/graph/{entityID}", 'highlight1,underline') 

            # summarize by data source
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

                # summarize by data source
                for dataSource in sorted(dataSources):
                    if dataSources[dataSource]:
                        recordData, entityData, otherData = self.formatRecords(dataSources[dataSource], reportType)
                        row = [recordData, entityData, otherData]
                    else:
                        row = [dataSource, ' ** suppressed ** ', '']
                    recordList.append(row)

            # display each record
            else:
                recordList = []
                for record in sorted(resolvedJson['RESOLVED_ENTITY']['RECORDS'], key=lambda k: (k['DATA_SOURCE'], k['RECORD_ID'])):
                    if dataSourceFilter and record['DATA_SOURCE'] not in dataSourceFilter:
                        additionalDataSources = True
                        continue
                    recordData, entityData, otherData = self.formatRecords(record, 'entityDetail')
                    row = [recordData, entityData, otherData]
                    recordList.append(row)

            # display if no relationships
            if relatedEntityCount == 0 or self.current_settings['show_relations_on_get'] == 'off':
                #if relatedEntityCount != 0:  #--must add this to table footer somehow
                #    print(f"{relatedEntityCount} related entities")
                self.renderTable(tblTitle, tblColumns, recordList)
                return 0

            # otherwise begin the report and add the relationships
            self.renderTable(tblTitle, tblColumns, recordList, displayFlag='begin')

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
                    relationship['DATA_SOURCES'].append(f"{colorize_dsrc(dataSource['DATA_SOURCE'])} ({dataSource['RECORD_COUNT']})")
                relationships.append(relationship)

            tblTitle = f"{relatedEntityCount} related entities"
            tblColumns = []
            tblColumns.append({'name': 'Entity ID', 'width': 15, 'align': 'left'})
            tblColumns.append({'name': 'Entity Name', 'width': 75, 'align': 'left'})
            tblColumns.append({'name': 'Data Sources', 'width': 75, 'align': 'left'})
            tblColumns.append({'name': 'Match Level', 'width': 25, 'align': 'left'})
            tblColumns.append({'name': 'Match Key', 'width': 50, 'align': 'left'})
            relatedRecordList = []
            for relationship in sorted(relationships, key=lambda k: k['MATCH_LEVEL']):
                row = []
                row.append(colorize_entity(str(relationship['ENTITY_ID'])))
                row.append(relationship['ENTITY_NAME'])
                row.append('\n'.join(sorted(relationship['DATA_SOURCES'])))
                row.append(self.relatedMatchLevels[relationship['MATCH_LEVEL']])
                matchData = {}
                matchData['matchKey'] = relationship['MATCH_KEY']
                matchData['ruleCode'] = self.getRuleDesc(relationship['ERRULE_CODE'])
                row.append(colorize_match_data(matchData))
                relatedRecordList.append(row)

            self.renderTable(tblTitle, tblColumns, relatedRecordList, titleJustify='l', displayFlag='end')

        return 0

    # ---------------------------
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

            # should only ever be one data source in the list
            dataSource = colorize_dsrc(record['DATA_SOURCE'])

            recordIdData = record['RECORD_ID']
            if reportType == 'detail':
                if record['MATCH_KEY']:
                    matchData = {}
                    matchData['matchKey'] = record['MATCH_KEY']
                    matchData['ruleCode'] = self.getRuleDesc(record['ERRULE_CODE'])
                    recordIdData += '\n' + colorize_match_data(matchData)
                if record['ERRULE_CODE']:
                    recordIdData += '\n  ' + colorize(self.getRuleDesc(record['ERRULE_CODE']), 'dim')
            recordIdList.append(recordIdData)

            for item in record['NAME_DATA']:
                if item.upper().startswith('PRIMARY'):
                    primaryNameList.append(colorize_attr(item))
                else:
                    otherNameList.append(colorize_attr('NAME: ' + item if ':' not in item else item))
            for item in record['ADDRESS_DATA']:
                addressList.append(colorize_attr('ADDRESS: ' + item if ':' not in item else item))
            for item in record['PHONE_DATA']:
                phoneList.append(colorize_attr('PHONE: ' + item if ':' not in item else item))
            for item in record['ATTRIBUTE_DATA']:
                attributeList.append(colorize_attr(item))
            for item in record['IDENTIFIER_DATA']:
                identifierList.append(colorize_attr(item))
            for item in sorted(record['OTHER_DATA']):
                if not self.isInternalAttribute(item) or reportType == 'detail':
                    otherList.append(colorize_attr(item))

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

    # ---------------------------
    def getFeatures(self, entityID):

        getFlagList = ['G2_ENTITY_INCLUDE_ALL_FEATURES']
        try:
            jsonData = execute_api_call('getEntityByEntityID', getFlagList, int(entityID))
        except Exception as err:
            print_message(err, 'error')
            return None

        g2_diagnostic_module = G2Diagnostic()
        if api_version_major > 2:
            g2_diagnostic_module.init('pyG2Diagnostic', iniParams, False)
        else:
            g2_diagnostic_module.initV2('pyG2Diagnostic', iniParams, False)

        # get the features in order
        orderedFeatureList = []
        for ftypeId in self.featureSequence:  # sorted(featureArray, key=lambda k: self.featureSequence[k]):
            ftypeCode = self.ftypeLookup[ftypeId]['FTYPE_CODE']
            for distinctFeatureData in jsonData['RESOLVED_ENTITY']['FEATURES'].get(ftypeCode, []):
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

            ftypeDisplay = colorize_attr(ftypeCode)
            if usageType:
                ftypeDisplay += f" ({usageType})"
            ftypeDisplay += '\n  ' + colorize(f'id: {libFeatId}', 'dim')

            # standardize the order of the attributes
            for i in range(len(jsonData['ELEMENTS'])):
                attrRecord = self.ftypeAttrLookup[ftypeCode].get(jsonData['ELEMENTS'][i]['FELEM_CODE'])
                attrId = attrRecord['ATTR_ID'] if attrRecord else 9999999
                jsonData['ELEMENTS'][i]['ATTR_ID'] = attrId

            felemDisplayList = []
            for elementData in sorted(sorted(jsonData['ELEMENTS'], key=lambda k: (k['FELEM_CODE'])), key=lambda k: (k['ATTR_ID'])):

                felem_value_display = elementData['FELEM_VALUE']
                if elementData['FELEM_CODE'] == 'LIBPOSTAL_PARSE':
                    with suppress(Exception): 
                        felem_value_dict = json.loads(elementData['FELEM_VALUE'])
                        felem_value_list = []
                        for key in sorted(felem_value_dict.keys()):
                            felem_value_list.append('  ' + colorize(key, 'highlight2,dim') + ': ' + json.dumps(felem_value_dict[key]))
                        felem_value_display = '\n' + '\n'.join(felem_value_list)
                felemDisplayList.append(colorize(elementData['FELEM_CODE'], 'highlight2') + ': ' + felem_value_display)

            tblRows.append([ftypeDisplay, featureDesc, '\n'.join(felemDisplayList)])
        return tblRows

    # ---------------------------
    def getAmbiguousEntitySet(self, entityId):
        # get other ambiguous relationships if this is the ambiguous entity
        getFlagList = ['G2_ENTITY_INCLUDE_ALL_FEATURES',
                       'G2_ENTITY_OPTION_INCLUDE_INTERNAL_FEATURES',
                       'G2_ENTITY_INCLUDE_ALL_RELATIONS',
                       'G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO']
        try:
            jsonData2 = execute_api_call('getEntityByEntityID', getFlagList, int(entityId))
        except Exception as err:
            print_message(err, 'error')
            return None

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

    # ---------------------------
    def help_compare(self):
        print(textwrap.dedent(f'''\

        Compares a set of entities by placing them side by side in a columnar format.

        {colorize('Syntax:', 'highlight2')}
            compare <entity_id1> <entity_id2>   {colorize('compares the listed entities', 'dim')}
            compare search                      {colorize('places all the search results side by side', 'dim')}
            compare search <top (n)>            {colorize('places the top (n) search results side by side', 'dim')}
       '''))


    # ---------------------------
    def do_compare(self, arg, **kwargs):
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'
        if not arg:
            self.help_compare()
            return -1 if calledDirect else 0

        # get possible data source list
        if 'dataSourceFilter' in kwargs and self.current_settings['data_source_suppression'] == 'on':
            dataSourceFilter = kwargs['dataSourceFilter']
        else:
            dataSourceFilter = None

        if type(arg) == str and 'SEARCH' in arg.upper():
            lastToken = arg.split()[len(arg.split()) - 1]
            if lastToken.isdigit():
                entityList = self.lastSearchResult[:int(lastToken)]
            else:
                entityList = self.lastSearchResult
        elif ',' in arg:
            entityList = arg.split(',')
        else:
            entityList = arg.split()

        if not all(x.isnumeric() for x in entityList) and not entityList[0].upper() in self.dsrcCodeLookup:
            print_message('Invalid parameter: expected one or more numeric entity IDs', 'caution')
            return -1 if calledDirect else 0


        getFlagList = ['G2_ENTITY_INCLUDE_ENTITY_NAME',
                       'G2_ENTITY_INCLUDE_RECORD_DATA',
                       'G2_ENTITY_INCLUDE_RECORD_MATCHING_INFO',
                       'G2_ENTITY_INCLUDE_RECORD_FORMATTED_DATA',
                       'G2_ENTITY_INCLUDE_ALL_RELATIONS',
                       'G2_ENTITY_INCLUDE_RELATED_ENTITY_NAME',
                       'G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO',
                       'G2_ENTITY_INCLUDE_RELATED_RECORD_SUMMARY']
        compareList = []
        entityList = list(set(entityList)) #--ensures a unique set of entities
        for entityId in entityList:
            try:
                jsonData = execute_api_call('getEntityByEntityID', getFlagList, int(entityId))
            except Exception as err:
                print_message(err, 'error')
                return -1 if calledDirect else 0

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
                        if not self.isInternalAttribute(item) and item not in entityData['otherData']:
                            entityData['otherData'].append(item)

            for relatedEntity in jsonData['RELATED_ENTITIES']:
                if relatedEntity['ENTITY_ID'] in entityList:
                    entityData['crossRelations'].append(relatedEntity)  # '%s\n %s\n to %s' % (relatedEntity['MATCH_KEY'][1:], relatedEntity['ERRULE_CODE'], relatedEntity['ENTITY_ID']))
                else:
                    entityData['otherRelations'].append(relatedEntity)  # {"MATCH_LEVEL": self.relatedMatchLevels[relatedEntity['MATCH_LEVEL']], "MATCH_KEY": relatedEntity['MATCH_KEY'][1:], "ERRULE_CODE": relatedEntity['ERRULE_CODE'], "ENTITY_ID": relatedEntity['ENTITY_ID'], "ENTITY_NAME": relatedEntity['ENTITY_NAME']})

            compareList.append(entityData)

        # determine if there are any relationships in common
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
                        if commonRelation and relation1 not in entityData1['relsInCommon']:
                            entityData1['relsInCommon'].append(relation1)

        # create the column data arrays
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
                    dataSourcesList.append(colorize_dsrc(dataSource + ': ' + recordID))
                if len(entityData['dataSources'][dataSource]) > 5:
                    dataSourcesList.append(dataSource + ': +%s more ' % str(len(entityData['dataSources'][dataSource]) - 5))
            dataSourcesRow.append('\n'.join(dataSourcesList))

            nameDataRow.append('\n'.join([colorize_attr(x) for x in sorted(entityData['nameData'])]))
            attributeDataRow.append('\n'.join([colorize_attr(x) for x in sorted(entityData['attributeData'])]))
            identifierDataRow.append('\n'.join([colorize_attr(x) for x in sorted(entityData['identifierData'])]))
            addressDataRow.append('\n'.join([colorize_attr(x) for x in sorted(entityData['addressData'])]))
            phoneDataRow.append('\n'.join([colorize_attr(x) for x in sorted(entityData['phoneData'])]))
            relationshipDataRow.append('\n'.join([colorize_attr(x) for x in sorted(entityData['relationshipData'])]))
            otherDataRow.append('\n'.join([colorize_attr(x) for x in sorted(entityData['otherData'])]))

            crossRelsList = []
            for relation in sorted(entityData['crossRelations'], key=lambda x: x['ENTITY_ID']):
                matchData = {}
                matchData['matchKey'] = relation['MATCH_KEY']
                matchData['ruleCode'] = self.getRuleDesc(relation['ERRULE_CODE'])
                if len(compareList) > 2:
                    matchData['entityId'] = relation['ENTITY_ID']
                crossRelsList.append(colorize_match_data(matchData))
            crossRelsRow.append('\n'.join(crossRelsList))

            commonRelsList = []
            for relation in sorted(entityData['relsInCommon'], key=lambda x: x['ENTITY_ID']):
                matchData = {}
                matchData['matchKey'] = relation['MATCH_KEY']
                matchData['ruleCode'] = self.getRuleDesc(relation['ERRULE_CODE'])
                matchData['entityId'] = relation['ENTITY_ID']
                matchData['entityName'] = relation['ENTITY_NAME']
                commonRelsList.append(colorize_match_data(matchData))
            commonRelsRow.append('\n'.join(commonRelsList))

        # initialize table
        columnWidth = 75

        tblTitle = 'Comparison of listed entities'
        tblColumns = []
        tblColumns.append({'name': 'Entity ID', 'width': 16, 'align': 'left'})
        urlRow = []
        for entityId in entityList:
            columnHeader = colorize_entity(str(entityId))
            tblColumns.append({'name': columnHeader, 'width': columnWidth, 'align': 'left'})
            if webapp_url:
                urlRow.append(colorize(f"{webapp_url}/graph/{entityId}", 'highlight1,underline'))

        # set the row titles
        rowTitles = {}
        rowTitles['urlRow'] = 'WebApp url'
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
            rowTitles[rowTitle] = colorize(rowTitles[rowTitle], 'row_title')

        # add the data
        tblRows = []
        if webapp_url:
            tblRows.append([rowTitles['urlRow']] + urlRow)
        tblRows.append([rowTitles['dataSourceRow']] + dataSourcesRow)
        if len(''.join(crossRelsRow)) > 0:
            tblRows.append([rowTitles['crossRelsRow']] + crossRelsRow)
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
        # if len(''.join(relationshipDataRow)) > 0:
        #    tblRows.append(['Disclosed Rels'] + relationshipDataRow)
        if len(''.join(commonRelsRow)) > 0:
            tblRows.append([rowTitles['commonRelsRow']] + commonRelsRow)

        self.renderTable(tblTitle, tblColumns, tblRows)

        return 0

    # ---------------------------
    def help_tree(self):
        print(textwrap.dedent(f'''\

        Displays an entity tree from a particular entity's point of view.

        {colorize('Syntax:', 'highlight2')}
            tree <entity_id>                  {colorize('displays the first degree relationships of an entity', 'dim')}
            tree <entity_id> degree <n>       {colorize('displays relationships of an entity out to <n> degrees', 'dim')}
            tree <entity_id> degree <n> all   {colorize('adding the "all" tag disables the default limit of 10 per category', 'dim')}
        '''))


    # ---------------------------
    def do_tree(self, arg, **kwargs):
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'
        if not arg:
            self.help_tree()
            return -1 if calledDirect else 0

        entityId = None
        buildOutDegree = 1
        max_children_display = 10
        argList = arg.split()
        if argList[-1].upper() == 'ALL':
            max_children_display = 999999
            argList.pop(-1)
        if len(argList) in (1, 3, 4):
            if argList[0].isdigit():
                entityId = int(argList[0])
            if len(argList) == 3 and argList[1].upper() == 'DEGREE' and argList[2].isdigit():
                buildOutDegree = int(argList[2])
        if not entityId:
            print_message('Invalid parameter: expected a numeric entity ID', 'warning')
            return

        entityParameter = json.dumps({'ENTITIES': [{'ENTITY_ID': entityId}]})

        # these are default thresholds
        maxDegree = 0  # really only used for entity paths
        maxEntities = 10000  # for safety

        getFlagList = ['G2_ENTITY_INCLUDE_ENTITY_NAME',
                       'G2_ENTITY_INCLUDE_RECORD_SUMMARY',
                       'G2_ENTITY_INCLUDE_ALL_RELATIONS',
                       'G2_ENTITY_INCLUDE_RELATED_MATCHING_INFO']
        try:
            json_data = execute_api_call('findNetworkByEntityID', getFlagList, [entityParameter, maxDegree, buildOutDegree, maxEntities])
        except Exception as err:
            print_message(err, 'error')
            return

        nodes = {}
        missing_entities = []

        current_parent_list = [{'NEXT_RELATED_ENTITY_I': 0, 'RELATED_ENTITY_LIST': [entityId], 'PRIOR_ENTITY_LIST': [entityId]}]
        while current_parent_list:

            # decrement degree if done with this list
            current_parent_data = current_parent_list[-1]
            if current_parent_data['NEXT_RELATED_ENTITY_I'] == len(current_parent_data['RELATED_ENTITY_LIST']):
                current_parent_list.pop()
                continue

            # get next related entity
            entity_id = current_parent_data['RELATED_ENTITY_LIST'][current_parent_data['NEXT_RELATED_ENTITY_I']]
            current_parent_list[-1]['NEXT_RELATED_ENTITY_I'] += 1
            nodes[entity_id] = {}
            nodes[entity_id]['RELATED_ENTITY_LIST'] = []

            entity_data = self.getEntityFromEntities(json_data['ENTITIES'], entity_id)
            if not entity_data:
                missing_entities.append(entity_id)
                nodes[entity_id]['ENTITY_NAME'] = 'not found!'
                continue

            nodes[entity_id]['ENTITY_NAME'] = entity_data['RESOLVED_ENTITY']['ENTITY_NAME']
            nodes[entity_id]['RECORD_SUMMARY'] = entity_data['RESOLVED_ENTITY']['RECORD_SUMMARY']
            nodes[entity_id]['RELATED_ENTITY_COUNT'] = 0
            nodes[entity_id]['DISCLOSED_RELATION_COUNT'] = 0
            nodes[entity_id]['DISCLOSED_RELATION_CATEGORIES'] = {}
            nodes[entity_id]['DERIVED_RELATION_COUNT'] = 0
            nodes[entity_id]['DERIVED_RELATION_CATEGORIES'] = {}

            # categorize relationships
            for relationship in entity_data.get('RELATED_ENTITIES', []):
                related_id = relationship['ENTITY_ID']

                # bypass nodes already rendered at prior levels
                if related_id in current_parent_list[-1]['PRIOR_ENTITY_LIST']:
                    continue

                nodes[entity_id]['RELATED_ENTITY_COUNT'] += 1
                nodes[entity_id]['RELATED_ENTITY_LIST'].append(related_id)

                disclosed_keys, derived_keys = self.categorizeMatchkey(relationship['MATCH_KEY'])

                if disclosed_keys:  # choose disclosed over derived
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

            # remove related entities at prior level
            related_entity_list = []
            if nodes[entity_id]['RELATED_ENTITY_LIST']:
                for related_id in nodes[entity_id]['RELATED_ENTITY_LIST']:
                    if related_id not in current_parent_list[-1]['PRIOR_ENTITY_LIST']:
                        related_entity_list.append(related_id)
                nodes[entity_id]['RELATED_ENTITY_LIST'] = related_entity_list

            # start a new parent if any children left
            if related_entity_list:
                current_parent_list.append({'ENTITY_ID': entity_id,
                                            'NEXT_RELATED_ENTITY_I': 0,
                                            'RELATED_ENTITY_LIST': related_entity_list,
                                            'PRIOR_ENTITY_LIST': current_parent_list[-1]['PRIOR_ENTITY_LIST'] + related_entity_list})
                #print('->', len(current_parent_list), entity_id, current_parent_list[-1])
        #print('----\n', json.dumps(nodes, indent=4), '\n----')

        # create the tree view
        tree_nodes = {}

        root_node = Node(entityId)
        root_node.node_desc = self.entityNodeDesc(nodes, entityId)
        tree_nodes[entityId] = root_node

        current_degree_list = [{'node': root_node, 'entity_id': entityId, 'next_child': 0}]
        while current_degree_list:

            # determine what relationships to build under a relationship class/category tree
            if current_degree_list[-1]['next_child'] == 0:
                # print('\t' * (len(current_degree_list) - 1), 'entity:', current_degree_list[-1]['entity_id'])
                entity_id = current_degree_list[-1]['entity_id']
                related_ids_to_build = []

                for relation_fields in [['DISCLOSED', 'DISCLOSED_RELATION_COUNT', 'DISCLOSED_RELATION_CATEGORIES'],
                                        ['DERIVED', 'DERIVED_RELATION_COUNT', 'DERIVED_RELATION_CATEGORIES']]:

                    class_name = relation_fields[0]
                    count_key = relation_fields[1]
                    category_key = relation_fields[2]

                    if nodes[entity_id][count_key] > 0:
                        class_node = Node(f'{nodes[entity_id]}-{class_name}')
                        # colorized_class_name = colorize(class_name, 'highlight1')
                        # class_node.node_desc = f'{colorized_class_name} ({nodes[entity_id][count_key]})'
                        class_node.node_desc = f'{class_name} ({nodes[entity_id][count_key]})'

                        category_color = 'highlight2' if class_name == 'DISCLOSED' else 'good'

                        for category in sorted(nodes[entity_id][category_key].keys()):
                            category_node = Node(f'{nodes[entity_id]}-{category}')
                            # colorized_category = colorize('+', 'highlight1' + ',dim').join(colorize(item, 'highlight1') for item in category.split('+'))
                            colorized_category = colorize('+'.join(category.split('+')), category_color)
                            category_node.node_desc = f'{colorized_category} ({len(nodes[entity_id][category_key][category])})'
                            cnt = 0
                            for related_id in sorted(nodes[entity_id][category_key][category]):
                                entity_node = Node(related_id)
                                entity_node.node_desc = self.entityNodeDesc(nodes, related_id)
                                tree_nodes[related_id] = entity_node
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

            # print('\t' * len(current_degree_list), 'related:', related_id, current_degree_list[-1]['prior_level_nodes'])

            # start a new list of children if any
            if len(current_degree_list) < buildOutDegree and nodes[related_id]['RELATED_ENTITY_COUNT'] > 0:
                current_degree_list.append({'node': tree_nodes[related_id], 'entity_id': related_id, 'next_child': 0})

        print()
        print(root_node.render_tree())
        print()

        return

    # ---------------------------
    def entityNodeDesc(self, nodes, nodeId):
        if nodeId not in nodes:
            return f'{nodeId} not found!'

        nodeDesc = colorize_entity(nodeId) + ' '

        if 'RECORD_SUMMARY' in nodes[nodeId]:
            nodeDesc += (' | '.join(colorize_dsrc(f"{ds['DATA_SOURCE']} ({ds['RECORD_COUNT']})") for ds in nodes[nodeId]['RECORD_SUMMARY']) + ' ')

        if 'ENTITY_NAME' in nodes[nodeId]:
            nodeDesc += (nodes[nodeId]['ENTITY_NAME'])
        else:
            nodeDesc += 'no name'

        return nodeDesc

    # ---------------------------
    def getEntityFromEntities(self, _entity_list, _entity_id):
        # print(json.dumps(_entity_list[0:100]))
        item_list = [item for item in _entity_list if item['RESOLVED_ENTITY']['ENTITY_ID'] == _entity_id]
        if item_list:
            return item_list[0]
        return None

    # ---------------------------
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
                    both_side_roles = this_key[this_key.find('(') + 1:this_key.find(')')].split(':')
                    # left side of colon is from this entity's point of view
                    # but if blank, must use right side as both sides not required
                    roles_to_use = both_side_roles[0] if both_side_roles[0] else both_side_roles[1]
                    disclosed_keys += roles_to_use.split(',')
            i += 1

        return disclosed_keys, derived_keys

    # ---------------------------
    def help_why(self):
        print(textwrap.dedent(f'''\

        Shows the interal values and scores used to determine why a set of records resolved or only related.

        {colorize('Syntax:', 'highlight2')}
            why <entity_id1>                                            {colorize('shows why the records in a single entity resolved together', 'dim')}
            why <entity_id1> <entity_id2>                               {colorize('shows why two or more different entities did not resolve', 'dim')}
            why <data_source1> <record_id1> <data_source2> <record_id2> {colorize('shows if the two data source records could resolve or relate', 'dim')}

        {colorize('Color legend:', 'highlight2')}
            {colorize('green', 'good')} indicates the values matched and contributed to the overall score
            {colorize('red', 'bad')} indicates the values did not match and hurt the overall score
            {colorize('yellow', 'caution')} indicates the values did not match but did not hurt the overall score
            {colorize('cyan', 'highlight2')} indicates the values only helped get the record on the candidate list
            {colorize('dimmed', 'dim')} values were ignored (see the bracket legend below)

        {colorize('Bracket legend:', 'highlight2')}
            [99] indicates how many entities share this value
            [~] indicates that this value was not used to find candidates as too many entities share it
            [!] indicates that this value was not not even scored as too many entities share it
            [#] indicates that this value was suppressed in favor of a more complete value\n
        '''))


    # ---------------------------
    def do_why(self, arg):
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'
        if not arg:
            self.help_why()
            return -1 if calledDirect else 0

        # see if already a list ... it will be if it came from audit
        if type(arg) == list:
            entityList = arg
        else:

            oldWhyNot = False
            if arg.upper().endswith(' OLD'):
                oldWhyNot = True
                arg = arg[0:-4]

            if type(arg) == str and 'SEARCH' in arg.upper():
                lastToken = arg.split()[len(arg.split()) - 1]
                if lastToken.isdigit():
                    entityList = self.lastSearchResult[:int(lastToken)]
                else:
                    entityList = self.lastSearchResult
            elif ',' in arg:
                entityList = arg.split(',')
            else:
                entityList = arg.split()

            if not all(x.isnumeric() for x in entityList) and not entityList[0].upper() in self.dsrcCodeLookup:
                print_message('Invalid parameter: expected one or more numeric entity IDs', 'caution')
                return -1 if calledDirect else 0

        if len(entityList) == 1:
            whyType = 'whyEntity'
            tblTitle = f"Why for entity: {colorize_entity(entityList[0])}"
            firstRowTitle = 'INTERNAL_ID'
            entityData = self.whyEntity(entityList)

        elif len(entityList) == 2 and not oldWhyNot:
            whyType = 'whyNot1'
            tblTitle = 'Why not for listed entities'
            firstRowTitle = 'ENTITY_ID'
            entityData = self.whyNot2(entityList)

        elif len(entityList) == 4 and entityList[0].upper() in self.dsrcCodeLookup:
            whyType = 'whyRecords'
            tblTitle = f"Why for record: {colorize_dsrc(entityList[0].upper())}: {entityList[1]} vs {colorize_dsrc(entityList[2].upper())}: {entityList[3]}"
            firstRowTitle = 'INTERNAL_ID'
            entityData = self.whyRecords(entityList)

        else:
            whyType = 'whyNot2'
            tblTitle = 'Why not for listed entities'
            firstRowTitle = 'ENTITY_ID'
            entityData = self.whyNotMany(entityList)

        if not entityData:
            return -1 if calledDirect else 0

        tblColumns = [{'name': colorize(firstRowTitle, 'row_title'), 'width': 50, 'align': 'left'}]
        tblRows = []

        dataSourceRow = ['DATA_SOURCES']
        matchKeyRow = ['WHY_RESULT']
        crossRelationsRow = ['RELATIONSHIPS']
        featureArray = {}
        for entityId in sorted(entityData.keys()):

            # add the column
            color = 'entity_color' if firstRowTitle == 'ENTITY_ID' else 'dim'
            tblColumns.append({'name': colorize(entityId, color), 'width': 75, 'align': 'left'})

            # add the data sources
            dataSourceRow.append('\n'.join(sorted(entityData[entityId]['dataSources'])))

            # add the cross relationships
            if 'crossRelations' in entityData[entityId]:
                relationList = []
                for relationship in [x for x in sorted(entityData[entityId]['crossRelations'], key=lambda k: k['entityId'])]:
                    if len(entityList) <= 2:  # supress to entity if only 2
                        del relationship['entityId']
                    relationList.append(colorize_match_data(relationship))
                crossRelationsRow.append('\n'.join(relationList))

            # add the matchKey
            if 'whyKey' not in entityData[entityId] or not entityData[entityId]['whyKey']:
                matchKeyRow.append(colorize('Not found!', 'bad'))
            elif type(entityData[entityId]['whyKey']) != list:
                matchKeyRow.append(colorize_match_data(entityData[entityId]['whyKey']))
            else:
                tempList = []
                for whyKey in [x for x in sorted(entityData[entityId]['whyKey'], key=lambda k: k['entityId'])]:
                    if 'entityId' in whyKey and len(entityList) <= 2:  # supress to entity if only 2
                        del whyKey['entityId']
                    tempList.append(colorize_match_data(whyKey))
                matchKeyRow.append('\n'.join(tempList))

            # prepare the feature rows
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

        # prepare the table
        tblRows.append(dataSourceRow)
        if len(crossRelationsRow) > 1:
            tblRows.append(crossRelationsRow)
        tblRows.append(matchKeyRow)

        # add the feature rows
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

        # colorize the first column
        for i in range(len(tblRows)):
            tblRows[i][0] = colorize(tblRows[i][0], 'row_title')

        # display the table
        self.renderTable(tblTitle, tblColumns, tblRows)

        return 0

    # ---------------------------
    def whyEntity(self, entityList):
        whyFlagList = ['G2_WHY_ENTITY_DEFAULT_FLAGS']
        try:
            jsonData = execute_api_call('whyEntityByEntityID', whyFlagList, int(entityList[0]))
        except Exception as err:
            print_message(err, 'error')
            return None

        entityData = {}
        for whyResult in jsonData['WHY_RESULTS']:
            internalId = whyResult['INTERNAL_ID']
            entityId = whyResult['ENTITY_ID']
            thisId = internalId  # will eventually be entityId when why not function is added
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

    # ---------------------------
    def whyRecords(self, entityList):
        whyFlagList = ['G2_WHY_ENTITY_DEFAULT_FLAGS']
        try:
            jsonData = execute_api_call('whyRecords', whyFlagList, [entityList[0], entityList[1], entityList[2], entityList[3]])
        except Exception as err:
            print_message(err, 'error')
            return None

        entityData = {}
        for whyResult in jsonData['WHY_RESULTS']:

            # get the first record
            internalId = whyResult['INTERNAL_ID']
            entityId = whyResult['ENTITY_ID']
            thisId = internalId  # will eventually be entityId when why not function is added
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

            # get the second record
            internalId = whyResult['INTERNAL_ID_2']
            entityId = whyResult['ENTITY_ID_2']
            thisId = internalId  # will eventually be entityId when why not function is added
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

            break  # there can only really be one, so lets be done!

        return entityData

    # ---------------------------
    def whyNot2(self, entityList):

        whyFlagList = ['G2_WHY_ENTITY_DEFAULT_FLAGS']
        try:
            jsonData = execute_api_call('whyEntities', whyFlagList, [int(entityList[0]), int(entityList[1])])
        except Exception as err:
            print_message(err, 'error')
            return None

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

        return entityData

    # ---------------------------
    def whyNotMany(self, entityList):

        whyFlagList = ['G2_WHY_ENTITY_DEFAULT_FLAGS',
                       'G2_ENTITY_INCLUDE_RECORD_JSON_DATA']

        masterFtypeList = []
        entityData = {}
        for entityId in entityList:
            entityData[entityId] = {}
            try:
                jsonData = execute_api_call('whyEntityByEntityID', whyFlagList, int(entityId))
            except Exception as err:
                print_message(err, 'error')
                return None

            # add the data sources and create search json
            searchJson = {}
            entityData[entityId]['dataSources'] = []
            for record in jsonData['ENTITIES'][0]['RESOLVED_ENTITY']['RECORDS']:
                entityData[entityId]['dataSources'].append('%s: %s' % (record['DATA_SOURCE'], record['RECORD_ID']))
                if not searchJson:
                    searchJson = record['JSON_DATA']
                else:  # merge the json records
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

            # get info for these features from the resolved entity section
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

            # see how this entity is related to the others
            getFlagList = ['G2_ENTITY_BRIEF_DEFAULT_FLAGS']
            try:
                jsonData2 = execute_api_call('getEntityByEntityID', getFlagList, int(entityId))
            except Exception as err:
                print_message(err, 'error')
                return

            entityData[entityId]['crossRelations'] = []
            for relatedEntity in jsonData2['RELATED_ENTITIES']:
                if relatedEntity['ENTITY_ID'] in entityList:
                    relationship = {}
                    relationship['entityId'] = relatedEntity['ENTITY_ID']
                    relationship['matchKey'] = relatedEntity['MATCH_KEY']
                    relationship['ruleCode'] = self.getRuleDesc(relatedEntity['ERRULE_CODE'])
                    entityData[entityId]['crossRelations'].append(relationship)

            # search for this entity to get the scores against the others
            searchFlagList = ['G2_SEARCH_INCLUDE_ALL_ENTITIES',
                              'G2_SEARCH_INCLUDE_FEATURE_SCORES',
                              'G2_ENTITY_INCLUDE_ENTITY_NAME',
                              'G2_ENTITY_INCLUDE_RECORD_DATA']
            try:
                jsonData2 = execute_api_call('searchByAttributes', searchFlagList, json.dumps(searchJson))
            except Exception as err:
                print_message(err, 'error')
                return

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
                        # get the best score for the feature
                        bestScoreRecord = None
                        for scoreRecord in resolvedEntityMatchInfo['FEATURE_SCORES'][featureCode]:
                            # print (json.dumps(scoreRecord, indent=4))
                            if not bestScoreRecord:
                                bestScoreRecord = scoreRecord
                            elif 'GNR_FN' in scoreRecord and scoreRecord['GNR_FN'] > bestScoreRecord['GNR_FN']:
                                bestScoreRecord = scoreRecord
                            elif 'BT_FN' in scoreRecord and scoreRecord['BT_FN'] > bestScoreRecord['BT_FN']:
                                bestScoreRecord = scoreRecord
                            elif 'FULL_SCORE' in scoreRecord and scoreRecord['FULL_SCORE'] > bestScoreRecord['FULL_SCORE']:
                                bestScoreRecord = scoreRecord
                        # update the entity feature
                        for libFeatId in entityData[entityId]['features']:
                            # print ('-' * 50)
                            # print(entityData[entityId]['features'][libFeatId])
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

        # find matching features whether scored or not (accounts for candidate keys as well)
        for entityId in entityList:
            for libFeatId in entityData[entityId]['features']:
                for entityId1 in entityList:
                    if entityId != entityId1 and libFeatId in entityData[entityId1]['features']:
                        entityData[entityId]['features'][libFeatId]['wasCandidate'] = 'Yes' if entityData[entityId]['features'][libFeatId]['isCandidate'] == 'Y' else 'No'
                        entityData[entityId]['features'][libFeatId]['matchScore'] = 100
                        entityData[entityId]['features'][libFeatId]['matchLevel'] = 'SAME'
                        break

        return entityData

    # ---------------------------
    def whyFmtRecordList(self, recordList):
        recordsBysource = {}
        for record in recordList:
            if record['DATA_SOURCE'] not in recordsBysource:
                recordsBysource[record['DATA_SOURCE']] = []
            recordsBysource[record['DATA_SOURCE']].append(record['RECORD_ID'])
        recordDisplay = []
        for dataSource in sorted(recordsBysource.keys()):
            coloredDataSource = colorize_dsrc(dataSource)
            if len(recordsBysource[dataSource]) > 1:
                recordDisplay.append(f'{coloredDataSource}: {len(recordsBysource[dataSource])} records')
            else:
                for recordId in sorted(recordsBysource[dataSource]):
                    recordDisplay.append(f'{coloredDataSource}: {recordId}')
        return recordDisplay

    # ---------------------------
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

    # ---------------------------
    def whyFormatFeature(self, featureData, whyKey):

        featureData['formattedFeatDesc'] = featureData['featDesc'].strip()
        ftypeCode = featureData['ftypeCode']
        featureData['counterDisplay'] = self.feature_counter_display(featureData)
        featureData['formattedFeatDesc'] += ' ' + featureData['counterDisplay']
        featureData['formattedFeatDesc1'] = featureData['formattedFeatDesc']

        dimmit = any(c in featureData['counterDisplay'] for c in ['~', '!', '#'])
        featureData['sortOrder'] = 3
        if 'wasScored' in featureData:
            if featureData['matchLevel'] in ('SAME', 'CLOSE'):
                featureData['sortOrder'] = 1
                featureData['featColor'] = 'good'
            else:
                featureData['sortOrder'] = 2
                if not whyKey:
                    featureData['featColor'] = 'bad'
                elif type(whyKey) == dict and ('-' + ftypeCode) not in whyKey['matchKey']:
                    featureData['featColor'] = 'caution'
                elif type(whyKey) == list and ('-' + ftypeCode) not in whyKey[0]['matchKey']:
                    featureData['featColor'] = 'caution'
                else:
                    featureData['featColor'] = 'bad'
            # if dimmit:
            #    featureData['featColor'] += ',dim'
            featureData['formattedFeatDesc1'] = featureData['formattedFeatDesc']
            featureData['formattedFeatDesc'] = colorize(featureData['formattedFeatDesc'], featureData['featColor'])

            # note: addresses may score same tho not exact!
            if featureData['matchLevel'] != 'SAME' or featureData['matchedFeatDesc'] != featureData['featDesc']:
                featureData['formattedFeatDesc'] += '\n' + colorize(f"\u2514\u2500\u2500 {featureData['matchedFeatDesc']} ({featureData['matchScoreDisplay']})", featureData['featColor'])

        elif 'matchScore' in featureData:  # must be same and likley a candidate builder
            featureData['sortOrder'] = 1
            featureData['featColor'] = 'highlight2' + (',dim' if dimmit else '')
            featureData['formattedFeatDesc1'] = featureData['formattedFeatDesc']
            featureData['formattedFeatDesc'] = colorize(featureData['formattedFeatDesc'], featureData['featColor'])

        else:
            if ftypeCode == 'AMBIGUOUS_ENTITY':
                if featureData['formattedFeatDesc'] .startswith(' ['):
                    featureData['formattedFeatDesc'] = 'Ambiguous!'
            featureData['formattedFeatDesc1'] = colorize(featureData['formattedFeatDesc'], 'bad')

        # sort rejected matches lower
        if dimmit:
            featureData['sortOrder'] += .5

        return featureData

    # ---------------------------
    def whyGetFeatures(self, jsonData, entityId, internalId=None):
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

    # ---------------------------
    def buildoutRecordFeatures(self, recordFeatures, featureData):
        features = {}
        for featRecord in recordFeatures:
            libFeatId = featRecord['LIB_FEAT_ID']
            usageType = featRecord.get('USAGE_TYPE', '')
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
                        # disabled here in favor of the record level usage type
                        # features[libFeatId]['usageType'] = distinctFeatureRecord.get('USAGE_TYPE','')
                        features[libFeatId]['featDesc'] = featRecord['FEAT_DESC']
                        features[libFeatId]['isCandidate'] = featRecord['USED_FOR_CAND']
                        features[libFeatId]['isScored'] = featRecord['USED_FOR_SCORING']
                        features[libFeatId]['entityCount'] = featRecord['ENTITY_COUNT']
                        features[libFeatId]['candidateCapReached'] = featRecord['CANDIDATE_CAP_REACHED']
                        features[libFeatId]['scoringCapReached'] = featRecord['SCORING_CAP_REACHED']
                        features[libFeatId]['scoringWasSuppressed'] = featRecord['SUPPRESSED']

        return features

    # ---------------------------
    def whyAddMatchInfo(self, features, matchInfo):

        whyKey = {}
        whyKey['matchKey'] = matchInfo['WHY_KEY']
        whyKey['ruleCode'] = self.getRuleDesc(matchInfo['WHY_ERRULE_CODE'])

        # update from candidate section of why
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

        # update from scoring section of why
        for ftypeCode in matchInfo['FEATURE_SCORES']:
            ftypeId = self.ftypeCodeLookup[ftypeCode]['FTYPE_ID']
            bestScoreRecord = {}
            for featRecord in matchInfo['FEATURE_SCORES'][ftypeCode]:
                # BUG WHERE INBOUND/CANDIDATE IS SOMETIMES REVERSED...
                if featRecord['INBOUND_FEAT_ID'] in features:
                    libFeatId = featRecord['INBOUND_FEAT_ID']
                    libFeatDesc = featRecord['INBOUND_FEAT']
                    matchedFeatId = featRecord['CANDIDATE_FEAT_ID']
                    matchedFeatDesc = featRecord['CANDIDATE_FEAT']
                elif featRecord['CANDIDATE_FEAT_ID'] in features:
                    # print(entityId, featRecord)
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

            if bestScoreRecord:  # and bestScoreRecord['libFeatId'] in features) or not : #--adjusted for how
                libFeatId = bestScoreRecord['libFeatId']
                if libFeatId not in features:  # adjusted for how
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

    # ---------------------------
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

    # ---------------------------
    def help_how(self):
        entity_id = colorize_entity('<entity_id>')
        print(textwrap.dedent(f'''\

            Shows shows how the records in a single entity came together.

            {colorize('Syntax:', 'highlight2')}
                how {entity_id}            {colorize('shows a summary of the resolution process', 'dim')}
                how {entity_id} concise    {colorize('shows the matching features as part of the tree view', 'dim')}
                how {entity_id} formatted  {colorize('shows the matching features in a table', 'dim')}

            {colorize('How to read:', 'highlight2')}
                A how report documents each step of the resoution process for an entity so if
                an entity has 100s records there will be 100s of steps. Each step will either
                create a virtual entity, add to it or combine it with other virtual entities
                that were created gotten created along the way.

                For instance, there may be a set of records (a virtual entity) that match on name
                and address and another set that match on name and phone before a record with the
                same name, address and phone combines the two virtual entities into one!

            {colorize('Pro tip!', 'good')}
                The overview section helps you locate interesting resolution steps based that you
                can search for in the concise or formatted view.  You can search for ...
                    - a particular step number such as step "2"
                    - a virtual entity_id such as {colorize_entity('V123-S2', 'dim')}
                        {colorize('(the -S number after the virtual entity ID is the step number that updated it.  Try', 'italics')}
                            {colorize('searching for just the V number before the dash to find all steps that include it.)', 'italics')}
                    - any other string such as a match_key, principle code, specific name, address, etc
             '''))

    # ---------------------------
    def do_how(self, arg):
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'
        if not arg:
            self.help_how()
            return -1 if calledDirect else 0

        how_display_level = 'overview'
        for level in ['summary', 'concise', 'formatted', 'verbose']:
            if level in arg:
                how_display_level = level
                arg = arg.replace(level, '').strip()

        try:
            entity_id = int(arg)
        except:
            print_message('Invalid parameter: expected a numeric entity ID', 'warning')
            return -1 if calledDirect else 0

        # do get first
        getFlagList = ['G2_ENTITY_INCLUDE_ENTITY_NAME',
                       'G2_ENTITY_INCLUDE_ALL_FEATURES',
                       'G2_ENTITY_OPTION_INCLUDE_FEATURE_STATS',
                       'G2_ENTITY_INCLUDE_RECORD_FEATURE_IDS']
        
        try:
            getEntityData = execute_api_call('getEntityByEntityID', getFlagList, int(entity_id))
        except Exception as err:
            print_message(err, 'error')
            return -1 if calledDirect else 0

        stat_pack = {'steps': {}, 'features': {}, 'rules': {}, 'ftype_counter': {}, 'rule_counter': {}}

        # build record feature matrix
        total_record_count = 0
        total_feature_count = 0
        features_by_record = {}
        for recordData in getEntityData['RESOLVED_ENTITY']['RECORDS']:
            total_record_count += 1
            if recordData['DATA_SOURCE'] not in features_by_record:
                features_by_record[recordData['DATA_SOURCE']] = {}
            features_by_record[recordData['DATA_SOURCE']][recordData['RECORD_ID']] = \
                self.buildoutRecordFeatures(recordData['FEATURES'], getEntityData['RESOLVED_ENTITY']['FEATURES'])

            # accumulate feature stats
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
                    for threshold in ['candidateCapReached', 'scoringCapReached', 'scoringWasSuppressed']:
                        if feature_data[threshold] == 'Y':
                            stat_pack['ftype_counter'][ftype_id][threshold] += 1
                else:
                    stat_pack['features'][ftype_id][feat_desc] += 1

        howFlagList = ['G2_HOW_ENTITY_DEFAULT_FLAGS']
        try:
            json_data = execute_api_call('howEntityByEntityID', howFlagList, int(entity_id))
        except Exception as err:
            print_message(err, 'error')
            return -1 if calledDirect else 0

        entity_name = getEntityData['RESOLVED_ENTITY'].get('ENTITY_NAME', 'name not mapped')
        how_header = '\n' + colorize(f"How report for entity {colorize_entity(entity_id)}: {entity_name}", 'table_title') + '\n'
        if json_data['HOW_RESULTS']['FINAL_STATE'].get('NEED_REEVALUATION', 0) or \
           len(json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES']) > 1:
            final_entity_count = len(json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES'])
            #print(json.dumps(json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES'], indent=4))
            how_header += '\n' + colorize(f'{final_entity_count} final entities, reevaluation needed!', 'bad') + '\n'
            # - maybe start with concise view if multiple
            # if how_display_level == 'overview'
            #     how_display_level = 'concise'

        # annotate steps and create aggregate dictionary
        stat_pack['largest_combine_steps'] = {}
        stat_pack['lowest_feature_scores'] = {}
        stat_pack['name_not_scored'] = []

        step_count = 0
        aggregate_nodes = {}
        resolution_steps = {}
        for step_data in json_data['HOW_RESULTS']['RESOLUTION_STEPS']:
            step_count += 1
            step_num = step_data['STEP']

            step_data['MATCH_INFO']['WHY_KEY'] = step_data['MATCH_INFO']['MATCH_KEY']
            step_data['MATCH_INFO']['WHY_ERRULE_CODE'] = step_data['MATCH_INFO']['ERRULE_CODE']
            for virtual_entity_num in ['VIRTUAL_ENTITY_1', 'VIRTUAL_ENTITY_2']:
                step_data[virtual_entity_num].update(self.get_virtual_entity_data(step_data[virtual_entity_num], features_by_record))
                features = step_data[virtual_entity_num]['features']
                why_key, features = self.whyAddMatchInfo(features, step_data['MATCH_INFO'])
                step_data[virtual_entity_num]['features'] = features

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
                lowest_member_count = step_data['VIRTUAL_ENTITY_1']['member_count'] if step_data['VIRTUAL_ENTITY_1']['member_count'] < step_data['VIRTUAL_ENTITY_2']['member_count'] else step_data['VIRTUAL_ENTITY_2']['member_count']
                total_member_count = step_data['VIRTUAL_ENTITY_1']['member_count'] + step_data['VIRTUAL_ENTITY_2']['member_count']
                if lowest_member_count not in stat_pack['largest_combine_steps']:
                    stat_pack['largest_combine_steps'][lowest_member_count] = [[step_num, total_member_count]]
                else:
                    stat_pack['largest_combine_steps'][lowest_member_count].append([step_num, total_member_count])
            else:
                step_data['step_type'] = 'Add record to virtual entity'

            if step_data['step_type'] not in stat_pack['steps']:
                stat_pack['steps'][step_data['step_type']] = 1
            else:
                stat_pack['steps'][step_data['step_type']] += 1

            step_data['MATCH_INFO']['matchKey'] = step_data['MATCH_INFO']['MATCH_KEY']
            step_data['MATCH_INFO']['ruleCode'] = self.getRuleDesc(step_data['MATCH_INFO']['ERRULE_CODE'])
            formatted_match_key, formatted_errule_code = colorize_match_data(step_data['MATCH_INFO']).split('\n ')
            step_data['MATCH_INFO']['formatted_match_key'] = formatted_match_key
            step_data['MATCH_INFO']['formatted_errule_code'] = formatted_errule_code
            if formatted_errule_code not in stat_pack['rules']:
                stat_pack['rules'][formatted_errule_code] = {}
                stat_pack['rule_counter'][formatted_errule_code] = 1
            else:
                stat_pack['rule_counter'][formatted_errule_code] += 1
            if formatted_match_key not in stat_pack['rules'][formatted_errule_code]:
                stat_pack['rules'][formatted_errule_code][formatted_match_key] = 1
            else:
                stat_pack['rules'][formatted_errule_code][formatted_match_key] += 1

            # format the features and find the lowest scoring
            for lib_feat_id in step_data['VIRTUAL_ENTITY_2']['features']:
                feature_data = step_data['VIRTUAL_ENTITY_2']['features'][lib_feat_id]
                feature_data = self.whyFormatFeature(feature_data, step_data['MATCH_INFO'])
                step_data['VIRTUAL_ENTITY_2']['features'][lib_feat_id] = feature_data

            name_was_scored = False
            for lib_feat_id in step_data['VIRTUAL_ENTITY_1']['features']:
                feature_data = step_data['VIRTUAL_ENTITY_1']['features'][lib_feat_id]
                feature_data = self.whyFormatFeature(feature_data, step_data['MATCH_INFO'])
                step_data['VIRTUAL_ENTITY_1']['features'][lib_feat_id] = feature_data

                ftype_id = feature_data['ftypeId']
                ftype_code = feature_data['ftypeCode']
                if feature_data.get('wasScored', 'No') == 'Yes' and ftype_code in step_data['MATCH_INFO']['MATCH_KEY']:
                    match_score = feature_data['matchScore']
                    if ftype_id not in stat_pack['lowest_feature_scores']:
                        stat_pack['lowest_feature_scores'][ftype_id] = {}
                    if match_score not in stat_pack['lowest_feature_scores'][ftype_id]:
                        stat_pack['lowest_feature_scores'][ftype_id][match_score] = [step_num]
                    else:
                        stat_pack['lowest_feature_scores'][ftype_id][match_score].append(step_num)
                    if ftype_code == 'NAME':
                        name_was_scored = True
            if not name_was_scored:
                stat_pack['name_not_scored'].append(step_num)

            resolution_steps[step_num] = step_data
            new_virtual_id = step_data.get('RESULT_VIRTUAL_ENTITY_ID', None)
            if new_virtual_id:
                # if new_virtual_id in aggregate_nodes:
                    # print(json.dumps(step_data, indent=4))
                    # print(f'\nunexpected: multiple steps for {new_virtual_id} {step_num} and ' + aggregate_nodes[new_virtual_id]['final_step'])
                    # input('wait')
                aggregate_nodes[new_virtual_id] = {'final_step': step_num, 'all_steps': []}

        # start from the end and combine the prior steps that just add another singleton
        orphan_final_entity_data = {}
        render_node_list = []
        for final_virtual_data in json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES']:
            final_virtual_id = final_virtual_data['VIRTUAL_ENTITY_ID']
            render_node_list.append({'node_id': final_virtual_id, 'parent_node': 'root'})

            current_aggregate_list = [final_virtual_id]
            while current_aggregate_list:
                current_node_id = current_aggregate_list[-1]

                # if there are no steps for this final node it became a orphan singleton
                if current_node_id not in aggregate_nodes:
                    orphan_final_entity_data[current_node_id] = self.get_virtual_entity_data(final_virtual_data, features_by_record)
                    current_aggregate_list.pop()
                else:
                    # keep going down chain until two singletons or two aggregates
                    aggregate_node_id = current_node_id
                    while True:
                        prior_step = aggregate_nodes[aggregate_node_id]['final_step']
                        aggregate_nodes[current_node_id]['all_steps'].append(prior_step)
                        if len(resolution_steps[prior_step]['aggregate_nodes']) == 1:
                            aggregate_node_id = resolution_steps[prior_step]['aggregate_nodes'][0]
                        else:
                            break

                    # if ended on step with two aggregates, each must be traversed
                    current_aggregate_list.pop()
                    if len(resolution_steps[prior_step]['aggregate_nodes']) == 2:
                        for aggregate_node_id in resolution_steps[prior_step]['aggregate_nodes']:
                            current_aggregate_list.append(aggregate_node_id)
                            render_node_list.append({'node_id': aggregate_node_id, 'parent_node': current_node_id})

        # create overview tree
        summary_node = Node('summary')
        summary_node.node_desc = colorize('SUMMARY', 'highlight1')

        resolution_node = Node('resolution')
        resolution_node.node_desc = self.how_format_statistic_header('RESOLUTION SUMMARY')
        summary_node.add_child(resolution_node)

        category_node = Node('steps')
        category_node.node_desc = self.how_format_statistic('Resolution steps', step_count)
        for item in stat_pack['steps']:
            item_node = Node(item)
            item_node.node_desc = colorize(self.how_format_statistic(item, stat_pack['steps'][item]), 'italics')
            category_node.add_child(item_node)
        resolution_node.add_child(category_node)

        interesting_step_list = []
        for step_num in stat_pack['name_not_scored']:
            interesting_step_list.append([step_num, 'name not scored'])
        for ftype_id in sorted(stat_pack['lowest_feature_scores']):
            ftype_code = self.ftypeLookup[ftype_id]['FTYPE_CODE']
            cntr = 0
            for lowest_score in sorted(stat_pack['lowest_feature_scores'][ftype_id]):
                if lowest_score < 90:
                    for step_num in stat_pack['lowest_feature_scores'][ftype_id][lowest_score]:
                        interesting_step_list.append([step_num, f"{ftype_code} scored {lowest_score}"])
                    cntr += 1
                if cntr == 2:
                    break
        cntr = 0
        for lowest_member_count in sorted(stat_pack['largest_combine_steps'], reverse=True):
            for large_step_info in sorted(stat_pack['largest_combine_steps'][lowest_member_count], key=lambda k: k[1], reverse=True):
                step_num = large_step_info[0]
                highest_member_count = large_step_info[1] - lowest_member_count
                interesting_step_list.append([step_num, f"Combines a group of {lowest_member_count} with a group of {highest_member_count}"])
            cntr += 1
            if cntr == 2:
                break
        if interesting_step_list:
            interesting_step_data = {}
            for step_num, reason in interesting_step_list:
                if step_num not in interesting_step_data:
                    interesting_step_data[step_num] = [reason]
                else:
                    interesting_step_data[step_num].append(reason)

            category_node = Node('interesting steps')
            category_node.node_desc = self.how_format_statistic('Steps of interest', len(interesting_step_data))
            for step_num in sorted(interesting_step_data.keys()):
                step_prefix = f"Step {step_num} - "
                interesting_step_node = Node(step_num)
                interesting_step_node.node_desc = ''
                for reason in interesting_step_data[step_num]:
                    interesting_step_node.node_desc += step_prefix + reason
                    step_prefix = ' ' * len(step_prefix)
                category_node.add_child(interesting_step_node)
            resolution_node.add_child(category_node)

        category_node = Node('rules')
        category_node.node_desc = 'Principles used'
        resolution_node.add_child(category_node)
        for rule_info in sorted(stat_pack['rule_counter'].items(), key=lambda item: item[1], reverse=True):
            rule = rule_info[0]
            rule_node = Node(rule)
            rule_cnt = colorize(f"({rule_info[1]})", 'highlight2')
            rule_node.node_desc = f"{rule} {rule_cnt}"
            category_node.add_child(rule_node)
            for match_key_info in sorted(stat_pack['rules'][rule].items(), key=lambda item: item[1], reverse=True):
                match_key = match_key_info[0]
                match_key_node = Node(match_key)
                match_key_cnt = colorize(f"({match_key_info[1]})", 'highlight2')
                match_key_node.node_desc = f"{match_key} {match_key_cnt}"
                rule_node.add_child(match_key_node)

        category_node = Node('entity')
        category_node.node_desc = self.how_format_statistic_header('ENTITY SUMMARY')
        summary_node.add_child(category_node)

        for stat_data in [['Total record count', total_record_count],
                          ['Total feature count', total_feature_count]]:
            item_node = Node(stat_data[0])
            item_node.node_desc = self.how_format_statistic(stat_data[0], stat_data[1])
            category_node.add_child(item_node)

        for ftype_id in sorted(stat_pack['features'], key=lambda k: self.featureSequence[k]):
            ftype_node = Node(ftype_id)
            ftype_cnt = colorize(f"({stat_pack['ftype_counter'][ftype_id]['featureCount']})", 'highlight2')
            ftype_node.node_desc = f"{colorize_attr(self.ftypeLookup[ftype_id]['FTYPE_CODE'])} {ftype_cnt}"
            category_node.add_child(ftype_node)
            feat_desc_info_list = sorted(stat_pack['features'][ftype_id].items(), key=lambda item: item[1], reverse=True)
            cnt = 0
            for feat_desc_info in feat_desc_info_list:
                cnt += 1
                if cnt in (1, 2, len(feat_desc_info_list), len(feat_desc_info_list) - 1):
                    feat_desc = feat_desc_info[0]
                    feat_node = Node(feat_desc)
                    feat_cnt = colorize(f"({feat_desc_info[1]})", 'highlight2')
                    if any(i in feat_desc for i in ['[~', '[!', '[#']):
                        feat_desc = colorize(feat_desc, 'dim')
                    feat_node.node_desc = f"{feat_desc} {feat_cnt}"
                    ftype_node.add_child(feat_node)
                elif cnt == 3 and len(feat_desc_info_list) > 4:
                    ftype_node.add_child(Node('~~~'))

        # start rendering nodes based on requested view and filter
        tree_nodes = {}
        filter_str = None
        while True:
            tree_nodes['root'] = Node('root')
            tree_nodes['root'].node_desc = colorize('RESOLUTION STEPS', 'bold')
            for render_node_data in render_node_list:
                render_node_id = render_node_data['node_id']
                parent_node_id = render_node_data['parent_node']

                # describe the node
                colored_node_id = colorize_entity(render_node_id)
                if parent_node_id == 'root':
                    num_final_nodes = len(json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES'])
                    final_node_index = 0
                    for final_state_data in json_data['HOW_RESULTS']['FINAL_STATE']['VIRTUAL_ENTITIES']:
                        final_node_index += 1
                        if final_state_data['VIRTUAL_ENTITY_ID'] == render_node_id:
                            break
                    if num_final_nodes == 1:
                        render_node_desc = colorize(f"{colored_node_id}: final entity", 'dim')
                    else:
                        render_node_desc = colorize(f"{colored_node_id}: final entity {final_node_index} of {num_final_nodes}", 'dim')
                else:
                    render_node_desc = colorize(f"{colored_node_id}: interim entity", 'dim')

                tree_nodes[render_node_id] = Node(render_node_id)
                tree_nodes[render_node_id].node_desc = render_node_desc
                tree_nodes[parent_node_id].add_child(tree_nodes[render_node_id])
                tree_nodes[render_node_id].add_parent(tree_nodes[parent_node_id])

                # there are no prior steps, this final node is a singleton
                if render_node_id not in aggregate_nodes:
                    orphan_entity_data = orphan_final_entity_data[render_node_id]
                    step_node_id = f"orphan-{render_node_id}"
                    tree_nodes[step_node_id] = Node(step_node_id)
                    tree_nodes[step_node_id].node_desc = 'Singleton'
                    tree_nodes[step_node_id].node_text = f"{orphan_entity_data['colored_desc']} {orphan_entity_data['entity_name']}"
                    tree_nodes[render_node_id].add_child(tree_nodes[step_node_id])
                    tree_nodes[step_node_id].add_parent(tree_nodes[render_node_id])

                # go through all the steps that built this node
                else:
                    for step_num in sorted(aggregate_nodes[render_node_id]['all_steps'], reverse=True):
                        step_data = resolution_steps[step_num]
                        step_node_id = f"Step {step_num}"
                        step_node_desc = step_node_id + ': ' + step_data['step_type']
                        step_node_desc += f" on {step_data['MATCH_INFO']['formatted_match_key']} {step_data['MATCH_INFO']['formatted_errule_code']}"

                        # always ensure lone singleton is on the left
                        if step_data['VIRTUAL_ENTITY_1']['node_type'] != 'singleton' and step_data['VIRTUAL_ENTITY_2']['node_type'] == 'singleton':
                            left_virtual_entity = 'VIRTUAL_ENTITY_2'
                            right_virtual_entity = 'VIRTUAL_ENTITY_1'
                        else:
                            left_virtual_entity = 'VIRTUAL_ENTITY_1'
                            right_virtual_entity = 'VIRTUAL_ENTITY_2'

                        left_features = step_data[left_virtual_entity]['features']
                        right_features = step_data[right_virtual_entity]['features']

                        # find the best matching record for each side
                        #  to make selection of best matching feature less arbitrary
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

                        # gather the features to display by type for each side
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

                                # get the best record keys for each side
                                matched_feat_id = feature_data.get('matchedFeatId')
                                if matched_feat_id:
                                    if best_record_key1 in features1[lib_feat_id]['record_list']:
                                        feature_data['record_key1'] = best_record_key1
                                    else:
                                        feature_data['record_key1'] = features1[lib_feat_id]['record_list'][0]

                                    if matched_feat_id not in features2:
                                        feature_data['record_key2'] = 'ERROR' + self.dsrc_record_sep + 'MISSING'
                                        input(f"wait {feature_data['record_key2']}")
                                    else:
                                        if best_record_key2 in features2[matched_feat_id]['record_list']:
                                            feature_data['record_key2'] = best_record_key2
                                        else:
                                            feature_data['record_key2'] = features2[matched_feat_id]['record_list'][0]

                                # skip unmatched if not showing full detail
                                elif how_display_level != 'verbose':
                                    continue

                                features_by_type[ftype_id][side].append(feature_data)

                        colored_virtual_id1 = colorize_entity(step_data[left_virtual_entity]['VIRTUAL_ENTITY_ID'], 'dim')
                        colored_virtual_id2 = colorize_entity(step_data[right_virtual_entity]['VIRTUAL_ENTITY_ID'], 'dim')

                        if how_display_level == 'concise':
                            step_node_desc += f"\n{colored_virtual_id1} {step_data[left_virtual_entity]['colored_desc']} {step_data[left_virtual_entity]['entity_name']}"
                            if not step_data['step_type'].startswith('Add'):
                                step_node_desc += f"\n{colored_virtual_id2} {step_data[right_virtual_entity]['colored_desc']} {step_data[right_virtual_entity]['entity_name']}"

                            step_node_text = ''
                            for ftypeId in sorted(features_by_type.keys(), key=lambda k: self.featureSequence[k]):
                                for featureData in sorted(sorted(features_by_type[ftypeId]['left'], key=lambda k: (k['featDesc'])), key=lambda k: (k['sortOrder'])):
                                    coloredFtypeCode = colorize_attr(featureData['ftypeCode'])
                                    coloredRecordKey1 = colorize_dsrc1(': '.join(featureData['record_key1'].split(self.dsrc_record_sep)))
                                    coloredRecordKey2 = colorize_dsrc1(': '.join(featureData['record_key2'].split(self.dsrc_record_sep)))
                                    coloredMatchScore = colorize(f"({featureData['matchScoreDisplay']})", featureData['featColor'])
                                    step_node_text += f"{coloredFtypeCode}: {coloredRecordKey1} - {featureData['featDesc']} | {coloredRecordKey2} - {featureData['matchedFeatDesc']} {coloredMatchScore}\n"
                        elif how_display_level != 'summary':
                            row_title = colorize('VIRTUAL_ID', 'dim')
                            tblTitle = None
                            tblColumns = []
                            tblColumns.append({'name': row_title, 'width': 20, 'align': 'left'})
                            tblColumns.append({'name': colored_virtual_id1, 'width': 70, 'align': 'left'})
                            tblColumns.append({'name': colorize('scores', 'dim'), 'width': 10, 'align': 'center'})
                            tblColumns.append({'name': colored_virtual_id2, 'width': 70, 'align': 'left'})
                            tblRows = []

                            row_title = colorize('DATA_SOURCES', 'row_title')
                            tblRow = [row_title]
                            for virtual_entity_data in [[left_virtual_entity, best_left_record_key],
                                                        [right_virtual_entity, best_right_record_key]]:
                                virtual_entity = virtual_entity_data[0]
                                best_record_key = virtual_entity_data[1]
                                if step_data[virtual_entity]['node_type'] == 'singleton':
                                    dsrc_display = step_data[virtual_entity]['colored_desc']
                                else:
                                    dsrc_display = step_data[virtual_entity]['node_desc'] + '\n best: ' + colorize_dsrc1(': '.join(best_record_key.split(self.dsrc_record_sep)))
                                tblRow.append(dsrc_display)
                            tblRow.insert(2, '')  # for score column
                            tblRows.append(tblRow)

                            for ftypeId in sorted(features_by_type.keys(), key=lambda k: self.featureSequence[k]):
                                if not features_by_type[ftypeId]['left'] and not features_by_type[ftypeId]['right']:
                                    continue  #  removes unscored if not full
                                ftype_code = self.ftypeLookup[ftypeId]['FTYPE_CODE']
                                colored_ftype_code = colorize_attr(ftype_code)

                                # get the right side values
                                scored_right = {}
                                unscored_right = []
                                for feature_data in sorted(sorted(features_by_type[ftypeId]['right'], key=lambda k: (k['featDesc'])), key=lambda k: (k['sortOrder'])):
                                    if feature_data.get('wasScored'):
                                        scored_right[feature_data['libFeatId']] = feature_data
                                    else:
                                        unscored_right.append(feature_data['formattedFeatDesc1'])

                                # add all the scored ones from the lefts point of view
                                unscored_left = []
                                for feature_data in sorted(sorted(features_by_type[ftypeId]['left'], key=lambda k: (k['featDesc'])), key=lambda k: (k['sortOrder'])):
                                    if feature_data.get('wasScored'):
                                        feature_score = '\n'.join(colorize(item, feature_data['featColor']) for item in feature_data['matchScoreDisplay'].split('|'))

                                        feature_desc1 = feature_data['formattedFeatDesc1']
                                        if step_data[left_virtual_entity]['node_type'] != 'singleton':
                                            from_desc = 'from: ' + colorize_dsrc1(': '.join(feature_data['record_key1'].split(self.dsrc_record_sep)))
                                            if feature_data['record_key1'] == best_left_record_key:
                                                from_desc = colorize(from_desc, 'dim')
                                            feature_desc1 += '\n ' + from_desc

                                        if feature_data['matchedFeatId'] not in scored_right:
                                            feature_desc2 = colorize(f"Internal error: {feature_data['matchedFeatId']} missing from {colored_virtual_id2}", 'bad')
                                            # input(feature_desc2 + ', press enter')
                                        else:
                                            feature_desc2 = scored_right[feature_data['matchedFeatId']]['formattedFeatDesc1']
                                        if step_data[right_virtual_entity]['node_type'] != 'singleton':
                                            from_desc = 'from: ' + colorize_dsrc1(': '.join(feature_data['record_key2'].split(self.dsrc_record_sep)))
                                            if feature_data['record_key2'] == best_right_record_key:
                                                from_desc = colorize(from_desc, 'dim')
                                            feature_desc2 += '\n ' + from_desc

                                        tblRows.append([colored_ftype_code, feature_desc1, feature_score, feature_desc2])
                                    else:
                                        unscored_left.append(feature_data['formattedFeatDesc1'])

                                if unscored_right or unscored_left:
                                    tblRows.append([colored_ftype_code, '\n'.join(unscored_left), '', '\n'.join(unscored_right)])

                            self.renderTable(tblTitle, tblColumns, tblRows, displayFlag='No')
                            step_node_text = self.currentRenderString

                        tree_nodes[step_node_id] = Node(step_node_id)
                        tree_nodes[step_node_id].node_desc = step_node_desc
                        tree_nodes[step_node_id].node_text = step_node_text
                        tree_nodes[render_node_id].add_child(tree_nodes[step_node_id])
                        tree_nodes[step_node_id].add_parent(tree_nodes[render_node_id])


            if how_display_level == 'overview':
                how_report = summary_node.render_tree(filter_str)
            elif tree_nodes['root'].children:  # will be no children if singleton
                if filter_str and filter_str.startswith('~node~'):
                    filter_str = filter_str[6:]
                    # steps don't actually have children, must go to the parent entity and show tree from there
                    if tree_nodes[filter_str].children:
                        parent_node = tree_nodes[filter_str]
                    else:
                        parent_node = tree_nodes[filter_str].parents[0]
                    if parent_node.parents:
                        parent_node = parent_node.parents[0]
                    if parent_node.node_id != 'root':
                        temp_node = Node('~~~')
                    else:
                        temp_node = parent_node
                    temp_node.add_child(parent_node)
                    how_report = temp_node.render_tree(filter_str)
                elif len(tree_nodes['root'].children) > 1:
                    tree_nodes['root'].node_desc = 'Final entities'
                    how_report = tree_nodes['root'].render_tree(filter_str)
                else:
                    how_report = tree_nodes['root'].children[0].render_tree(filter_str)
            else:
                how_report = 'There are no resolution steps to display!'

            if filter_str and filter_str not in how_report:
                input(f"\n{filter_str} was not found, press enter to continue")
                filter_str = None
            else:
                self.currentRenderString = how_header + ('\nFiltered for ' + colorize(filter_str, 'fg_white,bg_red') + '\n' if filter_str else '') + '\n' + how_report

            if filter_str:
                self.showTable(search=filter_str)
            else:
                self.showTable('auto')

            reply = input(colorize_prompt('\nSelect (O)verview, (C)oncise view, (F)ormatted view, (S)earch or (Q)uit ... '))
            if reply:
                removeFromHistory()
            else:
                continue

            if reply.upper() in ('Q', 'QUIT'):
                break
            elif reply.upper() == ('O'):
                how_display_level = 'overview'
                filter_str = None
            elif reply.upper() == ('C'):
                how_display_level = 'concise'
            elif reply.upper() == ('F'):
                how_display_level = 'formatted'
            elif reply.upper() == ('S'):
                if len(reply) > 1:
                    filter_str = reply[1:].strip()
                else:
                    filter_str = input('\nEnter a step number, a virtual entity ID, any other string or leave blank to clear filter ... ')
                    removeFromHistory()
            elif reply.isnumeric():
                filter_str = reply

            elif len(reply) > 1:
                filter_str = reply

            # check if they entered a valid step number
            if filter_str and filter_str.isnumeric():
                filter_str = f"Step {filter_str}"
                if filter_str not in tree_nodes:
                    input(f"\nStep {filter_str} not found, press enter to continue")
                    filter_str = None

            # check if they entered a node_id
            if filter_str and filter_str in tree_nodes:
                filter_str = f"~node~{filter_str}"

            if filter_str:
                how_display_level = 'concise' if how_display_level == 'overview' else how_display_level
        print()

        return

    # ---------------------------
    def get_virtual_entity_data(self, raw_virtual_entity_data, features_by_record):
        virtual_entity_data = {'id': raw_virtual_entity_data['VIRTUAL_ENTITY_ID']}
        virtual_entity_data['record_count'] = 0
        virtual_entity_data['member_count'] = 0
        virtual_entity_data['records'] = {}
        virtual_entity_data['features'] = {}
        bestNameCandidates = {'PRIMARY': '', 'OTHER': ''}
        for member_data in raw_virtual_entity_data['MEMBER_RECORDS']:
            virtual_entity_data['member_count'] += 1
            for record in sorted(member_data['RECORDS'], key=lambda k: k['DATA_SOURCE'] + k['RECORD_ID']):
                virtual_entity_data['record_count'] += 1
                if record['DATA_SOURCE'] not in virtual_entity_data['records']:
                    virtual_entity_data['records'][record['DATA_SOURCE']] = []
                virtual_entity_data['records'][record['DATA_SOURCE']].append(record['RECORD_ID'])

                # creates the master feature list for the virtual entity (accumulating which records have which features)
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

        # a member is an obs_ent, despite how many records it has
        if len(raw_virtual_entity_data['MEMBER_RECORDS']) == 1:
            additional_note = ''
            if virtual_entity_data['record_count'] > 1:  # its got addtional pure dupes
                additional_note = colorize(' +' + str(virtual_entity_data['record_count'] - 1) + ' pure dupes', 'dim')

            virtual_entity_data['node_type'] = 'singleton'
            record = raw_virtual_entity_data['MEMBER_RECORDS'][0]['RECORDS'][0]
            virtual_entity_data['node_desc'] = record['DATA_SOURCE'] + ': ' + record['RECORD_ID'] + additional_note
            virtual_entity_data['colored_desc'] = colorize_dsrc1(record['DATA_SOURCE'] + ': ' + record['RECORD_ID'] + additional_note)

        else:
            virtual_entity_data['node_type'] = 'aggregate'
            virtual_entity_data['node_desc'] = ' | '.join(colorize_dsrc1(ds + ' (' + str(len(virtual_entity_data['records'][ds])) + ')') for ds in sorted(virtual_entity_data['records'].keys()))
            virtual_entity_data['colored_desc'] = virtual_entity_data['node_desc']

        return virtual_entity_data

    # ---------------------------
    def how_format_statistic_header(self, header):
        return colorize(header, 'highlight2')

    # ---------------------------
    def how_format_statistic(self, stat, cnt):
        return stat + ' ' + colorize('(' + str(cnt) + ')', 'highlight2')

    # ---------------------------
    def help_score(self):
        print(textwrap.dedent(f'''\

        Compares any two features and shows the scores returned.

        {colorize('Syntax:', 'highlight2')}
            score [{'{'}"name_last": "Smith", "name_first": "Joseph"{'}'}, {'{'}"name_last": "Smith", "name_first": "Joe"{'}'}]
            score [{'{'}"addr_full": "111 First St, Anytown, USA"{'}'}, {'{'}"addr_full": "111 First Street, Anytown"{'}'}]
            score [{'{'}"passport_number": "1231234", "passport_country": "US"{'}'}, {'{'}"passport_number": "1231234", "passport_country": "USA"{'}'}]
        '''))


    # ---------------------------
    def do_score(self, arg):
        if not arg:
            self.help_score()
            return

        try:
            jsonData = json.loads(arg)
        except (ValueError, KeyError) as err:
            print_message(f"Invalid json parameter: {err}", 'error')
            return

        if type(jsonData) != list or len(jsonData) != 2:
            print_message(f"json parameter must be a list of two features to compare", 'error')
            return

        record1json = dictKeysUpper(jsonData[0])
        record2json = dictKeysUpper(jsonData[1])

        # use the test data source and entity type
        record1json['TRUSTED_ID_NUMBER'] = 'SCORE_TEST'
        record2json['TRUSTED_ID_NUMBER'] = 'SCORE_TEST'

        # add the records
        try:
            retcode = g2Engine.addRecord('TEST', 'SCORE_RECORD_1', json.dumps(record1json))
            retcode = g2Engine.addRecord('TEST', 'SCORE_RECORD_2', json.dumps(record2json))
        except G2Exception as err:
            print(str(err))
            return

        self.do_why('TEST SCORE_RECORD_1 TEST SCORE_RECORD_2')

        # delete the two temporary records
        try:
            retcode = g2Engine.deleteRecord('TEST', 'SCORE_RECORD_1')
            retcode = g2Engine.deleteRecord('TEST', 'SCORE_RECORD_2')
        except G2Exception as err:
            print_message(err, 'error')
            return

        return

    # ---------------------------
    def renderTable(self, tblTitle, tblColumns, tblRows, **kwargs):

        # display flags (start/append/done) allow for multiple tables to be displayed together and scrolled as one
        # such as an entity and its relationships

        # possible kwargs
        displayFlag = kwargs['displayFlag'] if 'displayFlag' in kwargs else None
        titleColor = kwargs['titleColor'] if 'titleColor' in kwargs else 'table_title'
        titleJustify = kwargs['titleJustify'] if 'titleJustify' in kwargs else 'l'  # left
        headerColor = kwargs['headerColor'] if 'headerColor' in kwargs else 'column_header'

        # setup the table
        tableWidth = 0
        columnHeaderList = []
        for i in range(len(tblColumns)):
            tableWidth += tblColumns[i]['width']
            tblColumns[i]['name'] = colorize(str(tblColumns[i]['name']), 'column_header')
            columnHeaderList.append(tblColumns[i]['name'])
        # tableObject = ColoredTable(title_color=titleColor, header_color=headerColor, title_justify=titleJustify)
        tableObject = PrettyTable()

        # tableObject.title = tblTitle
        tableObject.hrules = PRETTY_TABLE_ALL
        if pretty_table_style_available:
            tableObject.set_style(SINGLE_BORDER)
        else:
            tableObject.horizontal_char = '\u2500'
            tableObject.vertical_char = '\u2502'
            tableObject.junction_char = '\u253C'
        tableObject.field_names = columnHeaderList

        totalRowCnt = 0
        for row in tblRows:
            totalRowCnt += 1
            row[0] = '\n'.join([i for i in str(row[0]).split('\n')])
            if self.usePrettyTable:
                tableObject.add_row(row)
            else:
                tableObject.append_row(row)

        # format with data in the table
        for columnData in tblColumns:
            tableObject.max_width[str(columnData['name'])] = columnData['width']
            tableObject.align[str(columnData['name'])] = columnData['align'][0:1].lower()

        # write to a file so can be viewed with less
        # also write to the lastTableData variable in case cannot write to file
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
            if self.currentReviewList:
                self.currentRenderString = colorize(self.currentReviewList, 'bold') + '\n\n' + self.currentRenderString
            print('')
            self.showTable('auto')
            print('')
        return

    # ---------------------------
    def showTable(self, arg=None, **kwargs):
        if not self.currentRenderString:
            return

        # note: the F allows less to auto quit if output fits on screen
        #  if they purposely went into scroll mode, we should not auto-quit!
        if arg == 'auto':
            lessOptions = '-FMXSR'
        else:
            lessOptions = '-MXSR'

        #--start with a search
        search = kwargs.get('search')
        if search:
            lessOptions + ' /' + search

        # try pipe to less on small enough files (pipe buffer usually 1mb and fills up on large entity displays)
        less = subprocess.Popen(["less", lessOptions], stdin=subprocess.PIPE)
        try:
            less.stdin.write(self.currentRenderString.encode('utf-8'))
        except IOError:
            pass
        less.stdin.close()
        less.wait()

    # ---------------------------
    def help_export(self):
        print(textwrap.dedent(f'''\

        Exports the json records that make up the selected entities for debugging, reloading, etc.

        {colorize('Syntax:', 'highlight2')}
            export <entity_id>, <entity_id> degree <n> to <fileName> additive
            export search to <fileName>
            export search <search index> to <fileName>\n
        '''))


    # ---------------------------
    def do_export(self, arg):
        calledDirect = sys._getframe().f_back.f_code.co_name != 'onecmd'
        if not arg:
            self.help_export()
            return -1 if calledDirect else 0

        entityList = []
        fileName = None
        maxDegree = 0
        additive = False

        arg = arg.replace(',', ' ')
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
                        print_message('Invalid search index', 'error')
                        return -1 if calledDirect else 0
                    else:
                        entityList.append(self.lastSearchResult[int(lastToken) - 1])
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
                print_message(f"unknown command token: {thisToken}", 'warning')
            i += 1

        if not entityList:
            print_message('No entities found', 'warning')
            return

        if not fileName:
            if len(entityList) == 1:
                fileName = str(entityList[0]) + '.json'
            else:
                fileName = 'records.json'
        try:
            f = open(fileName, 'a' if additive else 'w')
        except IOError as err:
            print_message(err, 'error')
            return

        getFlagList = ['G2_ENTITY_INCLUDE_RECORD_DATA',
                       'G2_ENTITY_INCLUDE_RECORD_JSON_DATA']
        if maxDegree > 0:
            getFlagList.append('G2_ENTITY_INCLUDE_ALL_RELATIONS')

        exportedEntityList = []
        recordCount = 0
        currentDegree = 0
        currentEntityList = entityList
        while currentDegree <= maxDegree:
            nextEntityList = []
            for entityId in currentEntityList:
                exportedEntityList.append(entityId)

                try:
                    jsonData = execute_api_call('getEntityByEntityID', getFlagList, int(entityId))
                except Exception as err:
                    print_message(err, 'error')
                    return

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

        print_message(f"{recordCount} records written to {fileName}", 'success')

    # ---------------------------
    def getRuleDesc(self, erruleCode):
        return ('Principle ' + str(self.erruleCodeLookup[erruleCode]['ERRULE_ID']) + ': ' + erruleCode if erruleCode in self.erruleCodeLookup else '')

    # ---------------------------
    def getConfigData(self, table, field=None, value=None):

        recordList = []
        for i in range(len(self.cfgData['G2_CONFIG'][table])):
            if field and value:
                if self.cfgData['G2_CONFIG'][table][i][field] == value:
                    recordList.append(self.cfgData['G2_CONFIG'][table][i])
            else:
                recordList.append(self.cfgData['G2_CONFIG'][table][i])
        return recordList

    # ---------------------------
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

    # ---------------------------
    def isInternalAttribute(self, attrStr):
        if ':' in attrStr:
            attrStr = attrStr.split(':')[0]
        attrRecords = self.getConfigData('CFG_ATTR', 'ATTR_CODE', attrStr.upper())
        if attrRecords and attrRecords[0]['INTERNAL'].upper().startswith('Y'):
            return True
        return False


# --------------------------------------
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


# --------------------------------------
def fmtStatistic(amt):
    amt = int(amt)
    if amt > 1000000:
        return "{:,.2f}m".format(round(amt / 1000000, 2))
    else:
        return "{:,}".format(amt)


def printWithNewLines(ln, pos=''):

    pos.upper()
    if pos == 'S' or pos == 'START':
        print('\n' + ln)
    elif pos == 'E' or pos == 'END':
        print(ln + '\n')
    elif pos == 'B' or pos == 'BOTH':
        print('\n' + ln + '\n')
    else:
        print(ln)


# --------------------------------------
def dictKeysUpper(dict):
    return {k.upper(): v for k, v in dict.items()}


# --------------------------------------
def removeFromHistory(idx=0):
    if readline:
        if not idx:
            idx = readline.get_current_history_length() - 1
        readline.remove_history_item(idx)


# --------------------------------------
def _append_slash_if_dir(p):
    if p and os.path.isdir(p) and p[-1] != os.sep:
        return p + os.sep
    else:
        return p

# --------------------------------------
if __name__ == '__main__':
    appPath = os.path.dirname(os.path.abspath(sys.argv[0]))

    try:
        iniFileName = G2Paths.get_G2Module_ini_path()
    except:
        iniFileName = ''

    # capture the command line arguments
    argParser = argparse.ArgumentParser()
    argParser.add_argument('-c', '--config_file_name', dest='ini_file_name', default=iniFileName, help='name of the g2.ini file, defaults to %s' % iniFileName)
    argParser.add_argument('-s', '--snapshot_json_file', dest='snapshot_file_name', default=None, help='the name of a json statistics file computed by G2Snapshot.py')
    argParser.add_argument('-a', '--audit_json_file', dest='audit_file_name', default=None, help='the name of a json statistics file computed by G2Audit.py')
    argParser.add_argument('-w', '--webapp_url', dest='webapp_url', default=None, help='the url to the senzing webapp if available')
    argParser.add_argument('-D', '--debug_output', dest='debug_output', default=None, help='print raw api json to screen or <filename.txt>')
    argParser.add_argument('-H', '--histDisable', dest='histDisable', action='store_true', default=False, help='disable history file usage')

    args = argParser.parse_args()
    iniFileName = args.ini_file_name
    snapshotFileName = args.snapshot_file_name
    auditFileName = args.audit_file_name
    webapp_url = args.webapp_url
    debugOutput = args.debug_output
    hist_disable = args.histDisable

    # validate snapshot file if specified
    if snapshotFileName and not os.path.exists(snapshotFileName):
        print_message('Snapshot file not found', 'error')
        sys.exit(1)

    # validate audit file if specified
    if auditFileName and not os.path.exists(auditFileName):
        print_message('Audit file not found', 'error')
        sys.exit(1)

    # get parameters from ini file
    if not os.path.exists(iniFileName):
        print_message('n ini file was not found, please supply with the -c parameter', 'error')
        sys.exit(1)

    splash = colorize('\n  ____|  __ \\     \\    \n', 'DIM')
    splash += colorize('  __|    |   |   _ \\   ', 'DIM') + 'Senzing G2\n'
    splash += colorize('  |      |   |  ___ \\  ', 'DIM') + 'Exploratory Data Analysis\n'
    splash += colorize(' _____| ____/ _/    _\\ \n', 'DIM')
    prompt = '(g2) '
    print(splash)

    # get the version information
    try:
        g2Product = G2Product()
        api_version = json.loads(g2Product.version())
        api_version_major = int(api_version['VERSION'][0:1])
    except G2Exception as err:
        print_message(err, 'error')
        sys.exit(1)

    # try to initialize the g2engine
    try:
        g2Engine = G2Engine()
        iniParamCreator = G2IniParams()
        iniParams = os.getenv("SENZING_ENGINE_CONFIGURATION_JSON", iniParamCreator.getJsonINIParams(iniFileName))
        if api_version_major > 2:
            g2Engine.init('pyG2Explorer', iniParams, False)
        else:
            g2Engine.initV2('pyG2Explorer', iniParams, False)
    except Exception as err:
        print_message(err, 'error')
        sys.exit(1)

    # get needed config data
    try:
        g2ConfigMgr = G2ConfigMgr()
        if api_version_major > 2:
            g2ConfigMgr.init('pyG2ConfigMgr', iniParams, False)
        else:
            g2ConfigMgr.initV2('pyG2ConfigMgr', iniParams, False)
        defaultConfigID = bytearray()
        g2ConfigMgr.getDefaultConfigID(defaultConfigID)
        defaultConfigDoc = bytearray()
        g2ConfigMgr.getConfig(defaultConfigID, defaultConfigDoc)
        cfgData = json.loads(defaultConfigDoc.decode())
        g2ConfigMgr.destroy()
    except Exception as err:
        print_message(err, 'error')
        sys.exit(1)
    g2ConfigMgr.destroy()

    G2CmdShell().cmdloop()

    g2Engine.destroy()
    sys.exit()
