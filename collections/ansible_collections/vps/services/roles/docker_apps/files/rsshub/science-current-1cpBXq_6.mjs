import{t as e}from"./got-BwO5Bhij.mjs";import{t}from"./playwright-CEz1J9yL.mjs";import{n,r,t as i}from"./science-utils-COeEc3cs.mjs";import{load as a}from"cheerio";const o={path:`/current/:journal?`,categories:[`journal`],example:`/science/current/science`,parameters:{journal:`Short name for a journal`},features:{requireConfig:!1,requirePuppeteer:!0,antiCrawler:!0,supportBT:!1,supportPodcast:!1,supportScihub:!0},radar:[{source:[`science.org/journal/:journal`,`science.org/toc/:journal/current`],target:`/current/:journal`}],name:`Current Issue`,maintainers:[`y9c`,`TonyRL`],handler:s,description:`|  Short name |    Full name of the journal    | Route                                                                          |
| :---------: | :----------------------------: | ------------------------------------------------------------------------------ |
|   science   |             Science            | [/science/current/science](https://rsshub.app/science/current/science)         |
|    sciadv   |        Science Advances        | [/science/current/sciadv](https://rsshub.app/science/current/sciadv)           |
|  sciimmunol |       Science Immunology       | [/science/current/sciimmunol](https://rsshub.app/science/current/sciimmunol)   |
| scirobotics |        Science Robotics        | [/science/current/scirobotics](https://rsshub.app/science/current/scirobotics) |
|  signaling  |        Science Signaling       | [/science/current/signaling](https://rsshub.app/science/current/signaling)     |
|     stm     | Science Translational Medicine | [/science/current/stm](https://rsshub.app/science/current/stm)                 |

- Using route (\`/science/current/\` + "short name for a journal") to get current issue of a journal from AAAS.
- Leaving it empty (\`/science/current\`) to get update from Science.`};



async function s(o) {
    let { journal: s = "science" } = o.req.param();
    const feedUrl = "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=" + s;
    const { data: xml } = await e(feedUrl);
    const $ = a(xml, { xmlMode: true });
    const channelTitle = $("channel > title").text() || "Science: " + s;
    const channelDesc = $("channel > description").text() || "Table of Contents for " + s;
    const items = $("item").map((_, el) => {
        const itemEl = $(el);
        let dateText = "";
        for (const child of el.children || []) {
            if (child.name && child.name.toLowerCase().endsWith("date")) {
                dateText = $(child).text();
                break;
            }
        }
        return {
            title: itemEl.find("title").text(),
            link: itemEl.find("link").text(),
            description: itemEl.find("description").text(),
            pubDate: dateText
        };
    }).get();
    return {
        title: channelTitle,
        description: channelDesc,
        link: "https://www.science.org/journal/" + s,
        item: items
    };
}
export{o as route};