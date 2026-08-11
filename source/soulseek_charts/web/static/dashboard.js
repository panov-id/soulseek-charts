"use strict";

const PERIODS = ["day", "week", "month"];
const PERIOD_LABELS = { day: "Today", week: "This week", month: "This month" };
const PREVIOUS_LABELS = { day: "yesterday", week: "last week", month: "last month" };

/* ---------------------------------------------------------------- theme */

function applyStoredTheme() {
    const storedTheme = localStorage.getItem("theme");
    if (storedTheme) {
        document.documentElement.dataset.theme = storedTheme;
    }
}

function toggleTheme() {
    const root = document.documentElement;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const currentTheme = root.dataset.theme || (prefersDark ? "dark" : "light");
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    root.dataset.theme = nextTheme;
    localStorage.setItem("theme", nextTheme);
}

/* ----------------------------------------------------------------- data */

async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json();
}

/* ------------------------------------------------------------- elements */

function element(tagName, attributes = {}, children = []) {
    const node = document.createElement(tagName);
    for (const [name, value] of Object.entries(attributes)) {
        if (name === "class") {
            node.className = value;
        } else if (name === "text") {
            node.textContent = value;
        } else {
            node.setAttribute(name, value);
        }
    }
    for (const child of children) {
        node.append(child);
    }
    return node;
}

function movementCell(movement) {
    const labels = {
        up: `▲ ${movement.positions}`,
        down: `▼ ${Math.abs(movement.positions)}`,
        unchanged: "–",
        new: "new",
        re_entry: "re-entry",
    };
    const cell = element("td", { class: "movement " + movement.kind });
    cell.textContent = labels[movement.kind] ?? "–";
    return cell;
}

/* --------------------------------------------------------- chart tables */

function chartTable(entries, options) {
    const maximumSearches = Math.max(...entries.map((entry) => entry.searches), 1);

    const head = element("tr", {}, [
        element("th", { text: "#" }),
        element("th", { text: options.nameHeader }),
        element("th", { text: "" }),
        element("th", { class: "numeric", text: "Searches" }),
        element("th", { class: "numeric", text: "Listeners" }),
        element("th", { text: `vs ${options.previousLabel}` }),
    ]);

    const rows = entries.map((entry) => {
        const bar = element("div", { class: "bar" });
        bar.style.width = `${Math.max((entry.searches / maximumSearches) * 100, 2)}%`;

        const nameCell = element("td", { class: "name" });
        if (options.link) {
            nameCell.append(
                element("a", { href: options.link(entry), text: options.name(entry) })
            );
        } else {
            nameCell.textContent = options.name(entry);
        }

        return element("tr", {}, [
            element("td", { class: "position", text: String(entry.position) }),
            nameCell,
            element("td", { class: "bar-cell" }, [bar]),
            element("td", { class: "numeric", text: entry.searches.toLocaleString() }),
            element("td", { class: "numeric", text: entry.listeners.toLocaleString() }),
            movementCell(entry.movement),
        ]);
    });

    return element("div", { class: "table-scroll" }, [
        element("table", {}, [
            element("thead", {}, [head]),
            element("tbody", {}, rows),
        ]),
    ]);
}

/* ----------------------------------------------------------- line chart */

const CHART_WIDTH = 720;
const CHART_HEIGHT = 260;
const CHART_PADDING = { top: 16, right: 16, bottom: 28, left: 44 };

function svgElement(tagName, attributes) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tagName);
    for (const [name, value] of Object.entries(attributes)) {
        node.setAttribute(name, value);
    }
    return node;
}

const MAXIMUM_TICK_COUNT = 5;

// Smallest round step (1, 2 or 5 times a power of ten) that covers the data in
// at most five intervals, so ticks read as numbers a person would choose and
// the plot is not left half empty.
function niceScale(maximumValue) {
    for (let exponent = -2; exponent <= 9; exponent += 1) {
        for (const base of [1, 2, 5]) {
            const step = base * Math.pow(10, exponent);
            const tickCount = Math.ceil(maximumValue / step);
            if (tickCount <= MAXIMUM_TICK_COUNT) {
                return { step, tickCount: Math.max(tickCount, 1) };
            }
        }
    }
    return { step: maximumValue, tickCount: 1 };
}

// Above this many points a marker per observation turns the line into noise;
// the hover marker then carries point identity instead.
const DENSE_SERIES_THRESHOLD = 20;

function lineChart(points) {
    const frame = element("div", { class: "chart-frame" });
    if (points.length === 0) {
        frame.append(element("p", { class: "empty", text: "No activity in this range yet." }));
        return frame;
    }

    const series = [
        { key: "searches", label: "Searches", color: "var(--series-1)" },
        { key: "listeners", label: "Listeners", color: "var(--series-2)" },
    ];

    // Both series count the same kind of thing, so they share one axis.
    // Two scales on one chart would invent a relationship that is not there.
    const observedMaximum = Math.max(
        ...points.flatMap((point) => [point.searches, point.listeners]),
        1
    );
    const { step: tickStep, tickCount } = niceScale(observedMaximum);
    const maximumValue = tickStep * tickCount;
    const plotWidth = CHART_WIDTH - CHART_PADDING.left - CHART_PADDING.right;
    const plotHeight = CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom;

    const positionX = (index) =>
        CHART_PADDING.left +
        (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
    const positionY = (value) =>
        CHART_PADDING.top + plotHeight - (value / maximumValue) * plotHeight;

    const svg = svgElement("svg", {
        viewBox: `0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`,
        role: "img",
        "aria-label": "Daily searches and listeners",
    });

    for (let step = 0; step <= tickCount; step += 1) {
        const value = tickStep * step;
        const y = positionY(value);
        svg.append(
            svgElement("line", {
                x1: CHART_PADDING.left,
                x2: CHART_WIDTH - CHART_PADDING.right,
                y1: y,
                y2: y,
                stroke: step === 0 ? "var(--baseline)" : "var(--gridline)",
                "stroke-width": 1,
            })
        );
        const tick = svgElement("text", {
            x: CHART_PADDING.left - 8,
            y: y + 4,
            "text-anchor": "end",
            fill: "var(--text-muted)",
            "font-size": 11,
        });
        tick.textContent = Math.round(value).toLocaleString();
        svg.append(tick);
    }

    const firstLabel = svgElement("text", {
        x: CHART_PADDING.left,
        y: CHART_HEIGHT - 8,
        fill: "var(--text-muted)",
        "font-size": 11,
    });
    firstLabel.textContent = points[0].day.slice(0, 10);
    svg.append(firstLabel);

    const lastLabel = svgElement("text", {
        x: CHART_WIDTH - CHART_PADDING.right,
        y: CHART_HEIGHT - 8,
        "text-anchor": "end",
        fill: "var(--text-muted)",
        "font-size": 11,
    });
    lastLabel.textContent = points[points.length - 1].day.slice(0, 10);
    svg.append(lastLabel);

    const crosshair = svgElement("line", {
        y1: CHART_PADDING.top,
        y2: CHART_PADDING.top + plotHeight,
        stroke: "var(--baseline)",
        "stroke-width": 1,
        opacity: 0,
    });
    svg.append(crosshair);

    for (const definition of series) {
        const path = points
            .map(
                (point, index) =>
                    `${index === 0 ? "M" : "L"} ${positionX(index)} ${positionY(point[definition.key])}`
            )
            .join(" ");
        svg.append(
            svgElement("path", {
                d: path,
                fill: "none",
                stroke: definition.color,
                "stroke-width": 2,
                "stroke-linejoin": "round",
                "stroke-linecap": "round",
            })
        );

        // A ring in the surface colour keeps overlapping markers readable.
        if (points.length <= DENSE_SERIES_THRESHOLD) {
            points.forEach((point, index) => {
                svg.append(
                    svgElement("circle", {
                        cx: positionX(index),
                        cy: positionY(point[definition.key]),
                        r: 4,
                        fill: definition.color,
                        stroke: "var(--surface-1)",
                        "stroke-width": 2,
                    })
                );
            });
        }
    }

    const hoverMarkers = series.map((definition) => {
        const marker = svgElement("circle", {
            r: 5,
            fill: definition.color,
            stroke: "var(--surface-1)",
            "stroke-width": 2,
            opacity: 0,
        });
        svg.append(marker);
        return { definition, marker };
    });

    const tooltip = element("div", { class: "tooltip" });

    svg.addEventListener("mousemove", (event) => {
        const bounds = svg.getBoundingClientRect();
        const scale = CHART_WIDTH / bounds.width;
        const pointerX = (event.clientX - bounds.left) * scale;

        let nearestIndex = 0;
        let nearestDistance = Infinity;
        points.forEach((_, index) => {
            const distance = Math.abs(positionX(index) - pointerX);
            if (distance < nearestDistance) {
                nearestDistance = distance;
                nearestIndex = index;
            }
        });

        const point = points[nearestIndex];
        crosshair.setAttribute("x1", positionX(nearestIndex));
        crosshair.setAttribute("x2", positionX(nearestIndex));
        crosshair.setAttribute("opacity", 1);

        for (const { definition, marker } of hoverMarkers) {
            marker.setAttribute("cx", positionX(nearestIndex));
            marker.setAttribute("cy", positionY(point[definition.key]));
            marker.setAttribute("opacity", 1);
        }

        tooltip.textContent =
            `${point.day.slice(0, 10)} · ${point.searches} searches · ${point.listeners} listeners`;
        tooltip.classList.add("visible");
        tooltip.style.left = `${Math.min((positionX(nearestIndex) / scale) + 12, bounds.width - 220)}px`;
        tooltip.style.top = "8px";
    });

    svg.addEventListener("mouseleave", () => {
        crosshair.setAttribute("opacity", 0);
        for (const { marker } of hoverMarkers) {
            marker.setAttribute("opacity", 0);
        }
        tooltip.classList.remove("visible");
    });

    const legend = element("div", { class: "legend" });
    for (const definition of series) {
        const swatch = element("i");
        swatch.style.background = definition.color;
        legend.append(element("span", {}, [swatch, document.createTextNode(definition.label)]));
    }

    // The table view is the accessibility fallback for the plot above.
    const tableRows = points.map((point) =>
        element("tr", {}, [
            element("td", { text: point.day.slice(0, 10) }),
            element("td", { class: "numeric", text: String(point.searches) }),
            element("td", { class: "numeric", text: String(point.listeners) }),
        ])
    );
    const tableView = element("details", {}, [
        element("summary", { text: "Show as table" }),
        element("div", { class: "table-scroll" }, [
            element("table", {}, [
                element("thead", {}, [
                    element("tr", {}, [
                        element("th", { text: "Day" }),
                        element("th", { class: "numeric", text: "Searches" }),
                        element("th", { class: "numeric", text: "Listeners" }),
                    ]),
                ]),
                element("tbody", {}, tableRows),
            ]),
        ]),
    ]);

    frame.append(legend, svg, tooltip);
    const container = element("div", {}, [frame, tableView]);
    return container;
}

/* ---------------------------------------------------------------- views */

function periodControls(activePeriod) {
    const controls = element("div", { class: "controls" });
    for (const period of PERIODS) {
        const button = element("button", {
            type: "button",
            text: PERIOD_LABELS[period],
            "aria-pressed": String(period === activePeriod),
        });
        button.addEventListener("click", () => {
            window.location.hash = `#/?period=${period}`;
        });
        controls.append(button);
    }
    const exportLink = element("a", {
        href: `/api/v1/charts/artists.csv?period=${activePeriod}&page_size=200`,
        text: "Download CSV",
    });
    controls.append(exportLink);
    return controls;
}

async function renderCharts(view, period) {
    view.replaceChildren(periodControls(period), element("p", { class: "empty", text: "Loading…" }));

    const [artistChart, trackChart] = await Promise.all([
        fetchJson(`/api/v1/charts/artists?period=${period}&page_size=50`),
        fetchJson(`/api/v1/charts/tracks?period=${period}&page_size=50`),
    ]);

    const artistCard = element("section", { class: "card" }, [
        element("h2", { text: "Artists" }),
        element("p", {
            class: "caption",
            text: `${artistChart.period_start.slice(0, 10)} — ranked by searches, compared with ${PREVIOUS_LABELS[period]}`,
        }),
    ]);
    artistCard.append(
        artistChart.entries.length
            ? chartTable(artistChart.entries, {
                  nameHeader: "Artist",
                  previousLabel: PREVIOUS_LABELS[period],
                  name: (entry) => entry.artist_name,
                  link: (entry) => `#/artist/${encodeURIComponent(entry.artist_name)}`,
              })
            : element("p", { class: "empty", text: "Nothing collected for this period yet." })
    );

    const trackCard = element("section", { class: "card" }, [
        element("h2", { text: "Tracks" }),
        element("p", {
            class: "caption",
            text: `Ranked by searches, compared with ${PREVIOUS_LABELS[period]}`,
        }),
    ]);
    trackCard.append(
        trackChart.entries.length
            ? chartTable(trackChart.entries, {
                  nameHeader: "Track",
                  previousLabel: PREVIOUS_LABELS[period],
                  name: (entry) => `${entry.artist_name} — ${entry.track_name}`,
                  link: (entry) => `#/artist/${encodeURIComponent(entry.artist_name)}`,
              })
            : element("p", { class: "empty", text: "Nothing collected for this period yet." })
    );

    view.replaceChildren(periodControls(period), artistCard, trackCard);
}

async function renderArtist(view, artistName) {
    view.replaceChildren(element("p", { class: "empty", text: "Loading…" }));

    const detail = await fetchJson(`/api/v1/artists/${encodeURIComponent(artistName)}`);

    const historyCard = element("section", { class: "card" }, [
        element("h2", { text: detail.artist_name }),
        element("p", { class: "caption", text: "Daily searches over the last 90 days" }),
        lineChart(detail.history),
    ]);

    const trackRows = detail.top_tracks.map((track) =>
        element("tr", {}, [
            element("td", { class: "name", text: track.track_name }),
            element("td", { class: "numeric", text: track.searches.toLocaleString() }),
            element("td", { class: "numeric", text: track.listeners.toLocaleString() }),
        ])
    );

    const tracksCard = element("section", { class: "card" }, [
        element("h2", { text: "Most searched tracks" }),
        detail.top_tracks.length
            ? element("div", { class: "table-scroll" }, [
                  element("table", {}, [
                      element("thead", {}, [
                          element("tr", {}, [
                              element("th", { text: "Track" }),
                              element("th", { class: "numeric", text: "Searches" }),
                              element("th", { class: "numeric", text: "Listeners" }),
                          ]),
                      ]),
                      element("tbody", {}, trackRows),
                  ]),
              ])
            : element("p", { class: "empty", text: "No track-level searches recorded." }),
    ]);

    const backLink = element("p", {}, [element("a", { href: "#/", text: "← All charts" })]);

    view.replaceChildren(backLink, historyCard, tracksCard);
}

/* --------------------------------------------------------------- router */

async function route() {
    const view = document.getElementById("view");
    if (!view) {
        return;
    }

    const hash = window.location.hash.slice(1) || "/";
    try {
        if (hash.startsWith("/artist/")) {
            await renderArtist(view, decodeURIComponent(hash.slice("/artist/".length)));
            return;
        }
        const period = new URLSearchParams(hash.split("?")[1] || "").get("period") || "week";
        await renderCharts(view, PERIODS.includes(period) ? period : "week");
    } catch (error) {
        view.replaceChildren(
            element("p", { class: "empty", text: `Could not load the charts: ${error.message}` })
        );
    }
}

applyStoredTheme();
document.getElementById("theme-toggle")?.addEventListener("click", toggleTheme);
window.addEventListener("hashchange", route);
route();
