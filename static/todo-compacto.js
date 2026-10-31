(() => {
    if (document.documentElement.dataset.todoCompacto === "1") return;
    const edad = document.getElementById("edad");
    const descuento = document.getElementById("descuento");
    const descarga = document.getElementById("descargar-form");
    const meses = document.querySelector(".calendario-contenedor");
    if (!edad || !descuento || !descarga || !meses) return;
    document.documentElement.dataset.todoCompacto = "1";
    let calculadoras = edad.closest(".herramientas");
    if (!calculadoras || !calculadoras.contains(descuento)) {
        calculadoras = document.createElement("div"); calculadoras.className = "herramientas";
        edad.before(calculadoras); calculadoras.append(edad, descuento);
    }
    calculadoras.id = "calculadoras";
    let calendario = document.getElementById("calendario");
    if (!calendario) {
        calendario = document.createElement("section"); calendario.id = "calendario";
        meses.before(calendario);
        const heading = document.createElement("h2"); heading.textContent = `Calendario ${new Date().getFullYear()}`;
        const holder = document.createElement("div"); holder.className = "section-heading"; holder.append(heading);
        calendario.append(holder, meses);
        for (const h of document.querySelectorAll("body > h4")) if (h.textContent.includes("Calendario")) h.remove();
    }
    let header = document.querySelector(".app-header");
    if (!header) {
        header = document.createElement("header"); header.className = "app-header";
        header.innerHTML = '<div class="brand"><span class="brand-mark" aria-hidden="true">t.</span><div><h1>Tus herramientas</h1><p class="subtitle">Tu día, un poco más fácil.</p></div></div>';
        document.body.prepend(header);
    }
    let nav = header.querySelector("nav");
    if (!nav) { nav = document.createElement("nav"); header.append(nav); }
    nav.setAttribute("aria-label", "Herramientas"); nav.replaceChildren();
    for (const [card, title, icon] of [[edad,"Edad y signo","✦"],[descuento,"Descuento","%"],[descarga,"Descargar video o audio","↓"]]) {
        let heading = card.querySelector("h4,h2");
        if (heading) {
            heading.textContent = title;
            if (!heading.closest(".card-heading")) {
                const holder = document.createElement("div"); holder.className = "card-heading";
                const mark = document.createElement("span"); mark.className = "card-icon"; mark.setAttribute("aria-hidden","true"); mark.textContent = icon;
                heading.before(holder); holder.append(mark,heading);
            }
        }
    }
    for (const [selector, placeholder] of [["#fecha","dd/mm/aaaa"],["#monto","Monto"],["#porc","%"],["#url","Enlace del video o audio"]]) {
        const input = document.querySelector(selector);
        if (input) { input.placeholder = placeholder; input.setAttribute("aria-label",placeholder); }
    }
    const select = descarga.querySelector('select[name="download_type"]');
    const submit = descarga.querySelector('button[type="submit"],button');
    const message = document.getElementById("resultado-msg");
    const chips = document.createElement("div"); chips.className = "formato-opciones"; chips.setAttribute("role","group"); chips.setAttribute("aria-label","Formato de descarga");
    if (select && submit) {
        select.hidden = true;
        const label = descarga.querySelector(`label[for="${select.id}"]`); if (label) label.hidden = true;
        // Después del botón en el DOM para conservar los listeners antiguos que buscan el primer button.
        submit.closest("form").append(chips);
        for (const option of select.options) {
            const button = document.createElement("button"); button.type = "button"; button.textContent = option.textContent;
            button.setAttribute("aria-pressed",String(select.value === option.value));
            button.addEventListener("click",() => {
                select.value = option.value; select.dispatchEvent(new Event("change",{bubbles:true}));
                for (const chip of chips.children) chip.setAttribute("aria-pressed",String(chip === button));
            });
            chips.append(button);
        }
    }
    const panels = {calculadoras, descargas:descarga, calendario};
    const links = {};
    const isBusy = () => message?.getAttribute("aria-busy") === "true" || Boolean(submit?.disabled);
    const chosen = () => ["#edad","#descuento","#calculadoras"].includes(location.hash) ? "calculadoras" : ["#descargar-form","#descargas"].includes(location.hash) ? "descargas" : location.hash === "#calendario" ? "calendario" : "calculadoras";
    const show = (name) => {
        for (const [key,panel] of Object.entries(panels)) { panel.hidden = key !== name; links[key].setAttribute("aria-current",key === name ? "page" : "false"); }
    };
    for (const [key,title] of [["calculadoras","Calculadoras"],["descargas","Descargas"],["calendario","Calendario"]]) {
        const a = document.createElement("a"); a.href = `#${key}`; a.textContent = title; links[key] = a; nav.append(a);
        a.addEventListener("click",event => { event.preventDefault(); if (isBusy()) return; history.replaceState(null,"",`#${key}`); show(key); window.scrollTo(0,0); });
    }
    const busyState = () => {
        const busy = isBusy();
        for (const a of Object.values(links)) a.setAttribute("aria-disabled",String(busy));
        for (const chip of chips.children) chip.disabled = busy;
    };
    if (submit) new MutationObserver(busyState).observe(submit,{attributes:true,attributeFilter:["disabled"]});
    if (message) new MutationObserver(busyState).observe(message,{attributes:true,attributeFilter:["aria-busy"]});
    window.addEventListener("hashchange",() => { if (!isBusy()) show(chosen()); });
    show(chosen()); busyState();
    const footer = document.querySelector("footer"); if (footer) footer.textContent = "Todo · Hecho para tu día a día";
})();
