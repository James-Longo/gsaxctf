// GSA's official record boards, copied from James's Drive (read 2026-11-09):
//   Indoor:  "GSA Indoor Track Records" (Google Sheet 1aGgQTPSWmLqqeHuFV7sdD44gAq2536eCpbxOEl-kdP4),
//            year = the season's January
//   Outdoor: "GSA Outdoor Track Records.xlsx" (1j-0OrV1lANrIUZb65vuN3XvDOTL-BaiB), "GSA Records" sheet
// One record line per event and gender, marks rewritten in the site's format
// (5' 10" -> 5-10.00, 9:49.5(h) -> 9:49.5h). Re-copy when the boards change.
//
// The boards' events are the events every team's record board shows
// (BOARD_EVENTS); GSA's board is also cross-checked against its results.

const b = (gender, event, name, mark, year) => ({ gender, event, name, mark, year })

const GSA = {
  Indoor: [
    b('Boys', '55 Meter Dash', 'Ben Baldwin', '6.77', '2025'),
    b('Boys', '200 Meter Dash', 'Ben Baldwin', '24.03', '2025'),
    b('Boys', '400 Meter Dash', 'Wyatt Richardson', '52.84', '2025'),
    b('Boys', '800 Meter Run', 'John Hassett', '1:57.09', '2017'),
    b('Boys', '1 Mile Run', 'John Hassett', '4:25.20', '2017'),
    b('Boys', '2 Mile Run', 'John Hassett', '10:00.57', '2017'),
    b('Boys', '55 Meter Hurdles', 'Andrew Hipsky', '8.21', '2023'),
    b('Boys', '4x200 Meter Relay', 'Ben Baldwin, Jake Lepper, Fred Coit, Rowan Gagne', '1:36.48', '2025'),
    b('Boys', '4x800 Meter Relay', 'Addison Pellerano, Connor Meginnis, Caleb Hale, Keith Fisher', '9:07.92', '2007'),
    b('Boys', 'High Jump', 'Cameron Gordon', '5-10.00', '2016'),
    b('Boys', 'Pole Vault', 'Thomas Coolidge', '12-00.00', '2025'),
    b('Boys', 'Long Jump', 'Reece Renwick', '20-06.50', '2025'),
    b('Boys', 'Triple Jump', 'Reece Renwick', '42-10.50', '2026'),
    b('Boys', 'Shot Put', 'Charles St Lawrence', '35-00.50', '2023'),
    b('Girls', '55 Meter Dash', 'Ripley King-Ofsiany', '7.89', '2026'),
    b('Girls', '200 Meter Dash', 'Ripley King-Ofsiany', '27.70', '2026'),
    b('Girls', '400 Meter Dash', 'Logan Townsend', '1:04.14', '2025'),
    b('Girls', '800 Meter Run', 'Mary Brenna-Catus', '2:29.23', '2018'),
    b('Girls', '1 Mile Run', 'Thea Crowley', '5:19.69', '2022'),
    b('Girls', '2 Mile Run', 'Thea Crowley', '11:20.16', '2022'),
    b('Girls', '55 Meter Hurdles', 'Eliza Broughton', '9.44', '2018'),
    b('Girls', '4x200 Meter Relay', 'Hattie Slayton, Grace Broughton, Susanna Jakub, Lannea Zentz', '1:54.46', '2019'),
    b('Girls', '4x800 Meter Relay', 'Mary Brenna-Catus, Zeya Lorio, Mary Richardson, Eliza Broughton', '10:13.35', '2017'),
    b('Girls', 'High Jump', 'Ivy Manner-Wheeldon, Kathleen Stephens, Amelia Jackson', '4-10.00', '2019, 2024, 2025'),
    b('Girls', 'Pole Vault', 'Hazel Kimball', '7-00.00', '2026'),
    b('Girls', 'Long Jump', 'Ivy Manner-Wheeldon', '15-00.25', '2019'),
    b('Girls', 'Triple Jump', 'Ripley King-Ofsiany', '33-05.25', '2026'),
    b('Girls', 'Shot Put', 'Maranda Pert', '30-11.00', '2024'),
  ],
  Outdoor: [
    b('Boys', '100 Meter Dash', 'Rowan Gagne', '11.23', '2025'),
    b('Boys', '200 Meter Dash', 'Rowan Gagne', '22.57', '2025'),
    b('Boys', '400 Meter Dash', 'Wyatt Richardson', '52.37', '2025'),
    b('Boys', '800 Meter Run', 'Ben Plohr', '1:58.78', '2011'),
    b('Boys', '1600 Meter Run', 'John Hassett', '4:22.58', '2017'),
    b('Boys', '3200 Meter Run', 'James Johndrow', '9:49.5h', '1999'),
    b('Boys', '110 Meter Hurdles', 'Andrew Hipsky', '15.77', '2023'),
    b('Boys', '300 Meter Hurdles', 'Ben Plohr', '40.09', '2012'),
    b('Boys', '1600 Meter Race Walk', 'Erik Taylor-Lash', '6:56.32', '2017'),
    b('Boys', '4x100 Meter Relay', 'Ben Baldwin, Jake Lepper, Sayer Williams, Rowan Gagne', '45.13', '2024'),
    b('Boys', '4x400 Meter Relay', 'Ben Baldwin, Rowan Gagne, Fred Coit, Wyatt Richardson', '3:34.30', '2025'),
    b('Boys', '4x800 Meter Relay', 'Meredith Bradshaw-Thomas, Trent Williamson, John Hassett, Cameron Gordon', '8:25.19', '2017'),
    b('Boys', 'High Jump', 'Max Mattson', '6-04.00', '2017'),
    b('Boys', 'Pole Vault', 'Thomas Coolidge', '12-00.00', '2025'),
    b('Boys', 'Long Jump', 'Reece Renwick', '21-00.50', '2024'),
    b('Boys', 'Triple Jump', 'Max Mattson', '42-04.50', '2018'),
    b('Boys', 'Shot Put', 'Brandon Rafferty', '45-08.25', '2007'),
    b('Boys', 'Discus', 'Brandon Rafferty', '121-11', '2007'),
    b('Boys', 'Javelin', 'Finn Davis-Batt', '159-01', '2015'),
    b('Girls', '100 Meter Dash', 'Ripley King-Ofsiany', '13.38', '2026'),
    b('Girls', '200 Meter Dash', 'Ripley King-Ofsiany', '27.26', '2026'),
    b('Girls', '400 Meter Dash', 'Ripley King-Ofsiany', '58.36', '2026'),
    b('Girls', '800 Meter Run', 'Zeya Lorio', '2:27.29', '2017'),
    b('Girls', '1600 Meter Run', 'Thea Crowley', '5:12.34', '2022'),
    b('Girls', '3200 Meter Run', 'Thea Crowley', '10:47.85', '2022'),
    b('Girls', '100 Meter Hurdles', 'Deirdre Disney-Hoey', '16.03', '1995'),
    b('Girls', '300 Meter Hurdles', 'Grace Broughton', '48.75', '2021'),
    b('Girls', '1600 Meter Race Walk', 'Darlene Baker', '9:35.30', '1997'),
    b('Girls', '4x100 Meter Relay', 'Aurora Simmons, Logan Townsend, Leigh Carter, Ripley King-Ofsiany', '53.50', '2026'),
    b('Girls', '4x400 Meter Relay', 'Mazie Smallidge, Bella Cimeno, Zeya Lorio, Morgan Dauk', '4:18.60', '2016'),
    b('Girls', '4x800 Meter Relay', 'Zeya Lorio, Mary Richardson, Hanna Gutow, Eliza Broughton', '10:11.81', '2016'),
    b('Girls', 'High Jump', 'Danielle Baker', '5-02.00', '1995'),
    b('Girls', 'Pole Vault', 'Ava Sealander', '8-06.00', '2018'),
    b('Girls', 'Long Jump', 'Vika Grindle', '15-07.75', '2011'),
    b('Girls', 'Triple Jump', 'Ripley King-Ofsiany', '33-02.50', '2026'),
    b('Girls', 'Shot Put', 'Lee Ann Varnum', '32-08.25', '2019'),
    b('Girls', 'Discus', 'Maranda Pert', '115-01', '2021'),
    b('Girls', 'Javelin', 'Morgan Dauk', '119-11', '2017'),
  ],
}

export const OFFICIAL_BOARDS = { 'George Stevens Academy': GSA }

// "Gender|Event" keys of the events on the boards, per season
export const BOARD_EVENTS = Object.fromEntries(Object.entries(GSA).map(
  ([season, rows]) => [season, new Set(rows.map(r => `${r.gender}|${r.event}`))]))
