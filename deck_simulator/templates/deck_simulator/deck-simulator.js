// Cookie boilerplate from https://docs.djangoproject.com/en/3.1/ref/csrf/#ajax
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function getTokenSelector() {
	return document.getElementById("available-tokens");
}


function getCardSelector() {
	return document.getElementById("available-cards");
}

function getTotalConstraintsSection() {
	return document.getElementById("total-constraints-section");
}

function tagsData() {
	return JSON.parse(document.getElementById("available-tags-data").textContent);
}

function cardsData() {
	return JSON.parse(document.getElementById("available-cards-data").textContent);
}

function countConstraintsData() {
	return JSON.parse(document.getElementById("available_count_constraints").textContent);
}

function attachCardOption(parent, card) {
	const option = document.createElement("option");
	option.value = JSON.stringify(card);
	option.textContent = card.name;

	parent.append(option);
}

function loadAvailableCards(parent, house) {
	cardsData().filter(card => card.house === house).forEach(card =>
		attachCardOption(parent, card)
	);
}

function addCard(parent, card) {
	const cardListElem = document.createElement("li");
	cardListElem.dataset.cardData = card;
	cardListElem.textContent = JSON.parse(card).name;
	parent.append(cardListElem);
}

function addTagForm(parent, tags) {
	tags.forEach(tag => {
		const tagFormElem = document.createElement("input");
		tagFormElem.type = 'number';
		tagFormElem.id = `${parent.id}-${tag}`;
		tagFormElem.min = 0;
		tagFormElem.max = 36;

		const tagFormLabel = document.createElement("label");
		tagFormLabel.htmlFor = tag;
		tagFormLabel.textContent = tag;
		parent.append(tagFormLabel);
		parent.append(tagFormElem);
	})
}

function loadTotalConstraints() {
	const totalConstraintsSection = getTotalConstraintsSection();
	addTagForm(totalConstraintsSection, tagsData());
	addTagForm(totalConstraintsSection, countConstraintsData());
}

function addHouseSection(parentSection, house) {
	const newHouseSection = document.createElement("details")
	newHouseSection.id = `predefined-house-${house}`;
	const summary = document.createElement("summary");
	const heading = document.createElement("p");
	heading.textContent = house;
	heading.classList.add("deck-simulator__collapse-header");
	summary.append(heading);
	newHouseSection.append(summary);
	parentSection.append(newHouseSection);
	return newHouseSection;
}

function addConstraintsChoice(section, house) {
	const availableCards = document.createElement("select");
	availableCards.id = `available-cards-${house}`;
	loadAvailableCards(availableCards, house);

	const chosenCardsList = document.createElement("ul");
	chosenCardsList.id = `chosen-cards-list-${house}`;
	chosenCardsList.classList.add('deck-simulator__chosen-cards-list');
	chosenCardsList.style = "height: 100px; width: 300px; overflow: hidden; overflow-y: scroll";


	const addCardButton = document.createElement("button");
	addCardButton.id = `add-card-button-${house}`;
	addCardButton.textContent = 'Add';
	addCardButton.onclick = () => {
		addCard(chosenCardsList, availableCards.value);
	}

	section.append(availableCards);
	section.append(addCardButton);
	section.append(chosenCardsList);
	addTagForm(section, tagsData());
	addTagForm(section, countConstraintsData());
}

function loadHouseSelector() {
	const housesData = JSON.parse(document.getElementById("available-houses-data").textContent);
	const houseSelector = document.getElementById("available-houses");
	housesData.forEach(house => {
		const option = document.createElement("option");
		option.value = house;
		option.textContent = house;

		houseSelector.append(option);
	})

	const addHouseButton = document.getElementById("add-house-button");
	addHouseButton.onclick = () => {
		const house = houseSelector.value;
		const predefinedSection = document.getElementById("predefined-section");
		if (predefinedSection.querySelector(`#predefined-house-${house}`)) {
			return;
		}
		if (predefinedSection.querySelectorAll("details[id^=predefined-house]").length == 3) {
			return;
		}
		const newSection = addHouseSection(predefinedSection, house);
		addConstraintsChoice(newSection, house);
	}
}

function loadTokenSelector() {
	const tokenSelector = getTokenSelector();
	const tokenData = JSON.parse(document.getElementById("available-tokens-data").textContent);
	tokenData.forEach(token => attachCardOption(tokenSelector, token));

	const chooseTokenButton = document.getElementById("choose-token-button");
	chooseTokenButton.onclick = () => {
		const chosenTokenInfo = document.getElementById("chosen-token");
		const tokenData = JSON.parse(tokenSelector.value);
		chosenTokenInfo.dataset.chosenTokenId = tokenData.id;
		chosenTokenInfo.textContent = `Chosen token: ${tokenData.name}`;
	}
}

function getChosenTokenId() {
	return document.getElementById("chosen-token").dataset.chosenTokenId;
}

function getPredefinedCards() {
	const byHouse = {};
	const houseSections = document.querySelectorAll("details[id^=predefined-house]")
	houseSections.forEach(elem => {
		const house = elem.id.substring("predefined-house-".length);
		byHouse[house] = [];
		console.log(house);
		const chosenCardsElem = document.getElementById(`chosen-cards-list-${house}`);
		for (const child of chosenCardsElem.children) {
			const cardData = JSON.parse(child.dataset.cardData);
			byHouse[house].push(cardData.id);
		}
	})
	return byHouse;
}

function getMetaValues() {
	const meta = {
		'total': {
			'tagged': {}
		},
		'per_house': {
		}
	};

	const totalConstraintsSection = getTotalConstraintsSection();
	tagsData().forEach(tag => {
		const tagInput = document.getElementById(`${totalConstraintsSection.id}-${tag}`);
		if (tagInput.value) {
			meta.total.tagged[tag] = parseInt(tagInput.value);
		}
	});
	countConstraintsData().forEach(constraint => {
		const constraintInput = document.getElementById(`${totalConstraintsSection.id}-${constraint}`);
		if (constraintInput.value) {
			meta.total[constraint] = parseInt(constraintInput.value);
		}
	});

	const houseSections = document.querySelectorAll("details[id^=predefined-house]");
	houseSections.forEach(elem => {
		const house = elem.id.substring("predefined-house-".length);
		meta['per_house'][house] = {tagged: {}};
		tagsData().forEach(tag => {
			const tagInput = document.getElementById(`${elem.id}-${tag}`);
			if (tagInput.value) {
				meta['per_house'][house].tagged[tag] = parseInt(tagInput.value);
			}
		});
		countConstraintsData().forEach(constraint => {
			const constraintInput = document.getElementById(`${elem.id}-${constraint}`);
			if (constraintInput.value) {
				meta['per_house'][house][constraint] = parseInt(constraintInput.value);
			}
		});
	});

	return meta;
}

function setup() {
	loadTotalConstraints();
	loadHouseSelector();
	loadTokenSelector();

	const generateDeckButton = document.getElementById("generate-deck-button");
	generateDeckButton.onclick = () => {
		const predefined = getPredefinedCards();

		const token = getChosenTokenId();

		const meta = getMetaValues();

		const name = document.getElementById("deck-name-input").value;

		fetch("{% url 'deck-simulator' %}", {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'X-CSRFToken': getCookie('csrftoken')
			},
			body: JSON.stringify({
				predefined,
				meta,
				token,
				name
			})
		}).then(res => {
			if (res.status !== 200) {
				throw new Error("TODO");
			}
			return res.json();
		}).then(({ id }) => {
			window.location = id;
		}).catch(err => {
			console.log(err);
			// TODO
		})
	}
}

setup();
