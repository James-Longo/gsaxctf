
/**
 * Parses a track & field mark string into a numerical value for comparison.
 * Distances (19' 9.5") are converted to total inches (higher is better).
 * Times (7.24, 6:34.9) are converted to total seconds (lower is better).
 * Returns { value: number, isTime: boolean }
 */

/**
 * Parses a track & field mark string into a numerical value for comparison.
 * Distances (19' 9.5") are converted to total inches (higher is better).
 * Times (7.24, 6:34.9) are converted to total seconds (lower is better).
 * Invalid marks (DNF, DQ, NH, etc.) are flagged as invalid.
 * Returns { value: number, isTime: boolean, valid: boolean }
 */
export function parseMark(mark, forceDistance = false) {
    if (!mark) return { value: 0, isTime: true, valid: false };

    const s = mark.toUpperCase().trim();
    const BAD_MARKS = ['DNF', 'DNS', 'DQ', 'NH', 'ND', 'SCR', 'FOUL', 'X'];
    // Check if it is one of the bad marks (exact match or contained if typical format)
    // We'll be slightly aggressive: if it contains DNF/DNS/DQ/NH/ND, it's bad.
    if (BAD_MARKS.some(b => s === b || s.startsWith(b))) {
        return { value: 0, isTime: true, valid: false };
    }

    // Check for distance (contains ', ", or -) 
    // OR if forceDistance is true
    if (forceDistance || ((s.includes("'") || s.includes('"') || s.includes('-')) && /\d/.test(s))) {
        // Feet: digits followed by ' or -
        const feetMatch = s.match(/^(\d+)['\-]/) || s.match(/(\d+)'/);
        // Inches: digits after ' or - or space, possibly followed by "
        const inchesMatch = s.match(/['\-\s](\d+(\.\d+)?)/) || s.match(/(\d+(\.\d+)?)?"/);

        let totalInches = 0;
        if (feetMatch) totalInches += parseInt(feetMatch[1]) * 12;
        if (inchesMatch && inchesMatch[1]) totalInches += parseFloat(inchesMatch[1]);
        
        // Handle pure decimal/integer marks as feet if forceDistance is true
        if (!feetMatch && !inchesMatch && forceDistance) {
            const val = parseFloat(s);
            if (!isNaN(val)) totalInches = val * 12; // Assume feet
        }

        if (isNaN(totalInches)) return { value: 0, isTime: false, valid: false };

        return { value: totalInches, isTime: false, valid: true };
    }

    // Assume time
    // Clean up any non-time chars (like 'h' or 'c' suffixes sometimes seen?)
    // But be careful not to strip valid chars. 
    // Basic fallback:
    const parts = s.split(':').reverse();
    let totalSeconds = 0;

    // Check for obvious non-numeric
    if (s.match(/[A-Z]/)) {
        // If it still has letters and wasn't caught by BAD_MARKS, likely bad data or weird formatted time like "12.3h"
        // Let's try parsing digits.
    }

    // parts[0] is seconds, parts[1] is minutes, parts[2] is hours
    try {
        if (parts[0]) totalSeconds += parseFloat(parts[0]);
        if (parts[1]) totalSeconds += parseFloat(parts[1]) * 60;
        if (parts[2]) totalSeconds += parseFloat(parts[2]) * 3600;
    } catch (e) {
        return { value: 0, isTime: true, valid: false };
    }

    if (isNaN(totalSeconds) || totalSeconds === 0) return { value: 0, isTime: true, valid: false }; // 0.00 is unlikely valid except maybe start?

    return { value: totalSeconds, isTime: true, valid: true };
}

/**
 * Compares two marks. Returns true if a is better than b.
 */
export function isBetter(a, b, event = null) {
    const isDistance = event && isDistanceEvent(event);
    const pA = parseMark(a, isDistance);
    const pB = parseMark(b, isDistance);

    // If both invalid, neither is better
    if (!pA.valid && !pB.valid) return false;

    // If one is valid and other invalid, valid is better
    if (pA.valid && !pB.valid) return true;
    if (!pA.valid && pB.valid) return false;

    // Both valid: Compare values
    // Both valid: Must be same type to compare
    if (pA.isTime !== pB.isTime) return false;

    if (pA.isTime) {
        // Lower is better for time
        return pA.value < pB.value;
    } else {
        // Higher is better for distance
        return pA.value > pB.value;
    }
}

export function formatTime(seconds) {
    if (isNaN(seconds) || seconds === 0) return '';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins === 0) return secs.toFixed(2);
    const secStr = secs < 10 ? '0' + secs.toFixed(2) : secs.toFixed(2);
    return `${mins}:${secStr}`;
}

export function formatDistance(inches) {
    if (isNaN(inches) || inches === 0) return '';
    const ft = Math.floor(inches / 12);
    const ins = inches % 12;
    return `${ft}-${ins.toFixed(2)}`;
}

export const EVENT_MAP = {
    "100m Dash": ["100m Dash", "100 Meter Dash", "100 Dash"],
    "200m Dash": ["200m Dash", "200 Meter Dash", "200 Dash"],
    "400m Dash": ["400m Dash", "400 Meter Dash", "400 Dash"],
    "800m Run": ["800m Run", "800 Meter Run", "800 Run"],
    "1600m Run": ["1600m Run", "1600 Meter Run", "1600m", "1600 Meter"],
    "1 Mile Run": ["1 Mile Run", "1 Mile", "One Mile"],
    "3200m Run": ["3200m Run", "3200 Meter Run", "3200m", "3200 Meter"],
    "2 Mile Run": ["2 Mile Run", "2 Mile", "Two Mile"],
    "55m Dash": ["55m Dash", "55 Meter Dash"],
    "55m Hurdles": ["55m Hurdles", "55 Meter Hurdles"],
    "100m Hurdles": ["100m Hurdles", "100 Meter Hurdles"],
    "110m Hurdles": ["110m Hurdles", "110 Meter Hurdles"],
    "300m Hurdles": ["300m Hurdles", "300 Meter Hurdles"],
    "High Jump": ["High Jump"],
    "Pole Vault": ["Pole Vault"],
    "Long Jump": ["Long Jump"],
    "Triple Jump": ["Triple Jump"],
    "Shot Put": ["Shot Put"],
    "Discus": ["Discus", "Discus Throw"],
    "Javelin": ["Javelin", "Javelin Throw", "Javeline"],
    "Race Walk": ["Race Walk", "1600m Race Walk"],
    "4x100m Relay": ["4x100m", "4x100 Meter", "4x100"],
    "4x200m Relay": ["4x200m", "4x200 Meter", "4x200"],
    "4x400m Relay": ["4x400m", "4x400 Meter", "4x400"],
    "4x800m Relay": ["4x800m", "4x800 Meter", "4x800"]
};

export function normalizeEvent(event) {
    if (!event) return "Unknown";
    
    // 1. Gender Swap
    let normalized = event.replace(/\bMen\b/g, 'Boys').replace(/\bWomen\b/g, 'Girls');
    
    const lower = normalized.toLowerCase();
    for (const [standard, aliases] of Object.entries(EVENT_MAP)) {
        for (const alias of aliases) {
            const aliasLower = alias.toLowerCase();
            // Check for alias with word boundaries if possible, or just index
            if (lower.includes(aliasLower)) {
                // Replace the alias part with the standard name
                // This preserves prefixes like "Girls "
                const regex = new RegExp(alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
                return normalized.replace(regex, standard);
            }
        }
    }
    return normalized;
}

export function isDistanceEvent(event) {
    if (!event) return false;
    const normalized = normalizeEvent(event);
    return ["High Jump", "Pole Vault", "Long Jump", "Triple Jump", "Shot Put", "Discus", "Javelin"].includes(normalized);
}

