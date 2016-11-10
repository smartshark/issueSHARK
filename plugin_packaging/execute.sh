#!/bin/sh
PLUGIN_PATH=$1

COMMAND="python3.5 $1/main.py --db-user $2 --db-password $3 --db-database $4 --db-hostname $5 --db-port $6 --db-authentication $7 --url $8 --issueurl $9 --backend ${10}"

if [ ! -z ${10+x} ]; then
	COMMAND="$COMMAND --token ${11}"
fi

if [ ! -z ${12+x} ]; then
	if [ ! -z ${13+x} ]; then 
		COMMAND="$COMMAND --proxy-host ${12} --proxy-port ${13}"
		echo "$COMMAND"

		if [ ! -z ${14+x} ]; then
			if [ ! -z ${15+x} ]; then 
				COMMAND="$COMMAND --proxy-user ${14} --proxy-password ${15}"
				echo "$COMMAND"
			else
				echo "If proxy user is set, proxy password must also be set."
				return 1
			fi
		fi
	else
		echo "If proxy host is set, port must also be set."
		return 1
	fi
fi

$COMMAND
