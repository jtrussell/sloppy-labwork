document.addEventListener('alpine:init', () => {
  Alpine.data('questionBuilder', (configElementId) => {
    const config = JSON.parse(
      document.getElementById(configElementId).textContent,
    )

    return {
      questions: [],
      nextKey: 0,
      answerTypes: config.answer_types,
      choicePresets: config.choice_presets,
      maximumQuestions: config.maximum_questions,

      init() {
        this.questions = config.questions.map((entry) =>
          this.buildQuestion(entry),
        )
      },

      buildQuestion(entry) {
        return {
          key: this.nextQuestionKey(),
          id: entry.id || null,
          label: entry.label || '',
          description: entry.description || '',
          answer_type: entry.answer_type || 'text',
          is_required: Boolean(entry.is_required),
          choicesText: (entry.choices || []).join('\n'),
        }
      },

      get payload() {
        return JSON.stringify(
          this.questions.map((question) => ({
            id: question.id,
            label: question.label,
            description: question.description,
            answer_type: question.answer_type,
            is_required: question.is_required,
            choices: this.parseChoices(question.choicesText),
          })),
        )
      },

      parseChoices(choicesText) {
        return choicesText
          .split('\n')
          .map((choice) => choice.trim())
          .filter(Boolean)
      },

      canAddQuestion() {
        return this.questions.length < this.maximumQuestions
      },

      addQuestion() {
        if (!this.canAddQuestion()) return
        this.questions.push(this.buildQuestion({}))
        this.$nextTick(() => {
          const labelInputs = this.$root.querySelectorAll(
            '.ghostform-question-label',
          )
          labelInputs[labelInputs.length - 1]?.focus()
        })
      },

      removeQuestion(key) {
        this.questions = this.questions.filter(
          (question) => question.key !== key,
        )
      },

      handleSort(key, position) {
        const currentIndex = this.questions.findIndex(
          (question) => question.key === key,
        )
        if (currentIndex === -1 || currentIndex === position) return
        const reorderedQuestions = [...this.questions]
        const [movedQuestion] = reorderedQuestions.splice(currentIndex, 1)
        reorderedQuestions.splice(position, 0, movedQuestion)
        this.questions = reorderedQuestions.map((question) => ({
          ...question,
          key: this.nextQuestionKey(),
        }))
      },

      moveQuestion(key, offset) {
        const currentIndex = this.questions.findIndex(
          (question) => question.key === key,
        )
        const targetIndex = currentIndex + offset
        if (
          currentIndex === -1 ||
          targetIndex < 0 ||
          targetIndex >= this.questions.length
        )
          return
        const reorderedQuestions = [...this.questions]
        const [movedQuestion] = reorderedQuestions.splice(currentIndex, 1)
        reorderedQuestions.splice(targetIndex, 0, movedQuestion)
        this.questions = reorderedQuestions
      },

      nextQuestionKey() {
        this.nextKey += 1
        return this.nextKey
      },

      questionNumber(question) {
        return this.questions.indexOf(question) + 1
      },

      isMultipleChoice(question) {
        return question.answer_type === 'multiple_choice'
      },

      appendChoices(question, presetChoices) {
        const existingChoices = this.parseChoices(question.choicesText)
        const foldedChoices = new Set(
          existingChoices.map((choice) => choice.toLowerCase()),
        )
        const addedChoices = presetChoices.filter(
          (choice) => !foldedChoices.has(choice.toLowerCase()),
        )
        question.choicesText = [...existingChoices, ...addedChoices].join('\n')
      },
    }
  })
})
