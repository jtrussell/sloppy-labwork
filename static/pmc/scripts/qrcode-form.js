/**
 * QR Code Form
 *
 * Expected to be added to a page with the following elements:
 *  - #qr-reader: The element where the QR code reader will be displayed
 *  - #qr-code-message: The input element (typically hidden) where the QR code
 *    message will be stored
 *  - #qr-btn-start: The button to start the QR code reader
 *  - #qr-btn-stop: The button to stop the QR code reader
 *
 * Additionally, ensure the html5-qrcode library is loaded before this script.
 *
 * ```
 *   <script src="https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js" integrity="sha512-r6rDA7W6ZeQhvl8S7yRVQUKVHdexq+GAlNkNNqVC7YyIV+NwqCTJe2hDWCiffTyRNOeGEzRRJ9ifvRm/HCzGYg==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
 * ```
 */
;(function () {
  const qr = new Html5Qrcode('qr-reader')

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
    document.getElementById('qr-btn-start').style.display = 'none'
    document.getElementById('qr-btn-stop').style.display = 'inline'
  }

  function stopScan() {
    document.getElementById('qr-btn-start').style.display = 'inline'
    document.getElementById('qr-btn-stop').style.display = 'none'
    qr.stop()
  }

  document.getElementById('qr-btn-start').addEventListener('click', startScan)
  document.getElementById('qr-btn-stop').addEventListener('click', stopScan)
})()
