;(function () {
  const qr = new Html5Qrcode('qr-reader')
  const startButton = document.getElementById('qr-btn-start')
  const stopButton = document.getElementById('qr-btn-stop')

  function swapVisibleButton(buttonToShow, buttonToHide) {
    buttonToHide.hidden = true
    buttonToHide.style.display = 'none'
    buttonToShow.hidden = false
    buttonToShow.style.display = ''
  }

  function onScanSuccess(qrCodeMessage) {
    const input = document.getElementById('qr-code-message')
    input.value = qrCodeMessage
    input.closest('form').submit()
  }

  function onScanFailure() {}

  function startScan() {
    qr.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: 250 },
      onScanSuccess,
      onScanFailure
    )
    swapVisibleButton(stopButton, startButton)
  }

  function stopScan() {
    swapVisibleButton(startButton, stopButton)
    qr.stop()
  }

  startButton.addEventListener('click', startScan)
  stopButton.addEventListener('click', stopScan)
})()
