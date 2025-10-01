function copyLogsToClipboard() {
    const button = document.getElementById('copyLogsBtn');
    const originalText = button.textContent;
    const tournamentName = button.dataset.tournamentName || '';
    const logEntries = JSON.parse(button.dataset.logEntries || '[]');

    let logText = `Tournament Log: ${tournamentName}\n`;
    logText += `Generated: ${new Date().toLocaleString()}\n\n`;

    logEntries.forEach(log => {
        logText += `${log.date}\t${log.user}\t${log.action}${log.description ? ': ' + log.description : ''}\n`;
    });

    navigator.clipboard.writeText(logText).then(function() {
        button.textContent = 'Copied!';
        button.classList.add('button-success');

        setTimeout(function() {
            button.textContent = originalText;
            button.classList.remove('button-success');
        }, 2000);
    }).catch(function(err) {
        console.error('Failed to copy: ', err);
        button.textContent = 'Copy Failed';
        button.classList.add('button-danger');

        setTimeout(function() {
            button.textContent = originalText;
            button.classList.remove('button-danger');
        }, 2000);
    });
}
