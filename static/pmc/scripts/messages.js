(function () {
  const AUTO_DISMISS_DELAY_MS = 5000
  const FLASH_STORAGE_KEY = 'flashMessages'
  const MESSAGE_SELECTOR = '[data-message]'
  const PERSISTENT_LEVELS = ['error', 'warning']
  const TONE_CLASS_BY_LEVEL = {
    success: 'notice--success',
    info: 'notice--info',
    warning: 'notice--warning',
    error: 'notice--danger'
  }

  function isInUse(message) {
    return message.matches(':hover, :focus-within')
  }

  function dismissOnceIdle(message) {
    window.setTimeout(function () {
      if (isInUse(message)) {
        dismissOnceIdle(message)
      } else {
        message.remove()
      }
    }, AUTO_DISMISS_DELAY_MS)
  }

  function scheduleAutoDismiss(message) {
    if (!message.hasAttribute('data-message-persistent')) {
      dismissOnceIdle(message)
    }
  }

  function findLevel(tags) {
    const tagList = (tags || '').split(' ')
    return Object.keys(TONE_CLASS_BY_LEVEL).find(function (level) {
      return tagList.includes(level)
    })
  }

  function buildMessage(messageTemplate, messageData) {
    const message = messageTemplate.content.querySelector(MESSAGE_SELECTOR).cloneNode(true)
    const level = findLevel(messageData.tags)
    if (level) {
      message.classList.add(TONE_CLASS_BY_LEVEL[level])
      message.toggleAttribute('data-message-persistent', PERSISTENT_LEVELS.includes(level))
    }
    message.querySelector('[data-message-text]').innerHTML = messageData.message
    return message
  }

  function removeMessagesSaying(messageList, text) {
    messageList.querySelectorAll(MESSAGE_SELECTOR).forEach(function (shownMessage) {
      if (shownMessage.querySelector('[data-message-text]').textContent.trim() === text.trim()) {
        shownMessage.remove()
      }
    })
  }

  function showMessages(messagesData) {
    const messageList = document.getElementById('message-list')
    const messageTemplate = document.getElementById('message-template')
    if (!messageList || !messageTemplate) {
      return
    }
    messagesData.forEach(function (messageData) {
      const message = buildMessage(messageTemplate, messageData)
      removeMessagesSaying(messageList, message.querySelector('[data-message-text]').textContent)
      messageList.append(message)
      scheduleAutoDismiss(message)
    })
  }

  function parseTriggeredMessages(triggerHeader) {
    if (!triggerHeader || !triggerHeader.startsWith('{')) {
      return []
    }
    return JSON.parse(triggerHeader).messages || []
  }

  document.addEventListener('click', function (event) {
    const dismissButton = event.target.closest('[data-message-dismiss]')
    if (dismissButton) {
      dismissButton.closest(MESSAGE_SELECTOR).remove()
    }
  })

  document.addEventListener('htmx:afterRequest', function (event) {
    const triggerHeader = event.detail.xhr.getResponseHeader('HX-Trigger')
    const isRedirect = !!event.detail.xhr.getResponseHeader('HX-Redirect')
    if (isRedirect) {
      const isJsonTrigger = !!triggerHeader && triggerHeader.startsWith('{')
      window.localStorage.setItem(FLASH_STORAGE_KEY, isJsonTrigger ? triggerHeader : '{}')
    } else {
      showMessages(parseTriggeredMessages(triggerHeader))
    }
  })

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('#message-list ' + MESSAGE_SELECTOR).forEach(scheduleAutoDismiss)
    showMessages(parseTriggeredMessages(window.localStorage.getItem(FLASH_STORAGE_KEY)))
    window.localStorage.removeItem(FLASH_STORAGE_KEY)
  })

  window.keychainShowMessages = showMessages
})()
