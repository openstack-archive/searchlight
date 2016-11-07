#!/usr/bin/env bash

# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Take an OpenStack translated portable object (*.po) file and translate
# all of the message strings back into English using Google Translate.
# Allows for a quick examination of the translation.
#
# Each translated message has the following format:
#
#    msgid "Confirm Delete Instance"
#    msgid_plural "Confirm Delete Instances"     (Optional)
#    msgstr "Подтвердите удаление инстанса"      (Optional)
#    msgstr[0] "Подтвердите удаление инстанса"   (Optional)
#    msgstr[1] "Подтвердите удаление инстансов"  (Optional)
#    msgstr[2] "Подтвердите удаление инстансов"  (Optional)
#
# This gives us:
# - The original message in the "msgid/msgid_plural" line(s).
# - The translated message in the "msgstr/msgstr[*]" line(s).
#
# After untranslating, we will output the following:
# - The "msgid/msgid_plural" line(s).
# - The "msgstr/msgstr[*]" line(s).
# - The translation of the "msgstr/msgstr[*]" line(s).
#
# The engine of this script is "trans" (which itself uses gawk). We will
# need to install "trans" for this script to work.
#     % wget git.io/trans
#     % chmod a+x trans
#  Make sure the "trans" script is in your PATH.

Usage="\
Usage: $0 [-s] [-t <lang>] file
Where:
    [-t <lang>] : Specify the target language to translate the
                  document. The default is English ("en").
    [-s]        : Use the language declared in the document for
                  the source language (\"Language:\" field). The default
                  is to not specify a  language and let "trans" figure
                  it out.
    file        : The OpenStack translation document.
"

find_src="0"   # Default: Do not specify the source language.
target="en"    # Default: Use English as the target language.

# Parse parameters
while getopts "t:sh?" opt
do
    case $opt in
        s) find_src="1"
           ;;
        t) target=$OPTARG
           ;;
        h) printf "$Usage"
           exit 0
           ;;
   esac
done

# Get the file (.po) to translate.
shift $((OPTIND-1))
file=$1

if [ -z "$file" ]
then
    printf "$Usage"
    exit 1
fi

if [ "${find_src}" = "1" ]
then
     # Tell the translator which language to use.
    source=`grep "Language:" $file | sed "s/^.*: //" | sed "s/\\\\\n.*$//"`
else
    # Let the translator determine the language.
    source=""
fi

cat $file | while read line
do
    if [[ "$line" == msgid* ]]
    then
        if [[ "$line" == msgid_plural* ]]
        then
            msgid_plural=`echo $line | sed "s/^msgid_plural \"//" | sed "s/\".*$//"`
        else
            msgid=`echo $line | sed "s/^msgid \"//" | sed "s/\".*$//"`
            msgid_plural=""
        fi
    elif [[ "$line" == msgstr* ]]
    then
        if [[ "$line" == msgstr\[* ]]
        then
            msgstr=`echo $line | sed "s/^msgstr\[.*\] \"//" | sed "s/\".*$//"`
        else
            msgstr=`echo $line | sed "s/^msgstr \"//" | sed "s/\".*$//"`
        fi

        # Translate. Use '--' in case the msgstr is '-'.
        translate=`trans -b ${source}:${target} -- "$msgstr"`
        echo ""
        echo "msgid: $msgid"
        if [[ "$msgid_plural" ]]
        then
            echo "msgid_plural: $msgid_plural"
        fi
        echo "msgstr: $msgstr"
        echo "Translation: $translate"
    fi
done

exit 0
