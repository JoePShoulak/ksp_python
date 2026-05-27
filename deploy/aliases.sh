# Source this file from bash to add KSP shortcuts:
# source deploy/aliases.sh
#
# Then use:
# deploy
# up
# down
# restart

alias deploy='bash deploy/manage.sh deploy'
alias bootstrap='bash deploy/manage.sh bootstrap'
alias up='bash deploy/manage.sh up'
alias down='bash deploy/manage.sh down'
alias restart='bash deploy/manage.sh restart'

# Backwards-compatible helpers.
alias source-deploy='bash deploy/manage.sh send'
alias apply-deploy='bash deploy/apply-deploy.sh'
