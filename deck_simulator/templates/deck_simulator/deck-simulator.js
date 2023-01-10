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


function getCardSelector() {
	return document.getElementById("available-cards");
}

function getPredefinedCards() {
	return document.getElementById("chosen-cards-list");
}

function loadAvailableCards() {
	const cardsData = JSON.parse(document.getElementById("available-cards-data").textContent);
	const selector = getCardSelector();
	cardsData.forEach(card => {
		const option = document.createElement("option");
		option.value = JSON.stringify(card);
		option.textContent = card.name;

		selector.append(option);
	})
}

function addCard(card) {
	const predefinedCards = getPredefinedCards();
	const cardListElem = document.createElement("li");
	cardListElem['card-data'] = card;
	cardListElem.textContent = JSON.parse(card).name;
	predefinedCards.append(cardListElem);
}

function setup() {
	loadAvailableCards();

	const addCardButton = document.getElementById("add-card-button");
	addCardButton.onclick = () => {
		const selector = getCardSelector();
		const card = selector.value;
		addCard(card);
	}

	const generateDeckButton = document.getElementById("generate-deck-button");
	generateDeckButton.onclick = () => {
		const houses = {};
		const predefinedCards = getPredefinedCards();
		for (const child of predefinedCards.children) {
			const cardData = JSON.parse(child['card-data']);
			if (!houses[cardData.house]) {
				houses[cardData.house] = [];
			}
			houses[cardData.house].push(cardData.id);
		}

		const meta = {};
		fetch("{% url 'deck-simulator' %}", {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'X-CSRFToken': getCookie('csrftoken')
			},
			body: JSON.stringify({
				houses,
			})
		}).then(res => {
			if (res.status === 200) return res.blob();
		}).then(blob => {
			var newBlob = new Blob([blob], {type: "application/pdf"});
			const data = window.URL.createObjectURL(newBlob);
			  var link = document.createElement('a');
			  link.href = data;
			  link.download="file.pdf";
			  link.click();
			  setTimeout(function(){
			    // For Firefox it is necessary to delay revoking the ObjectURL
			    window.URL.revokeObjectURL(data);
			  }, 100);
		});
	}
}

setup();