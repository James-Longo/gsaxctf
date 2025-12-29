
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
export function parseMark(mark) {
    if (!mark) return { value: 0, isTime: true, valid: false };

    const s = mark.toUpperCase().trim();
    const BAD_MARKS = ['DNF', 'DNS', 'DQ', 'NH', 'ND', 'SCR', 'FOUL', 'X'];
    // Check if it is one of the bad marks (exact match or contained if typical format)
    // We'll be slightly aggressive: if it contains DNF/DNS/DQ/NH/ND, it's bad.
    if (BAD_MARKS.some(b => s === b || s.startsWith(b))) {
        return { value: 0, isTime: true, valid: false };
    }

    // Check for distance (contains ', ", or -) 
    // BUT ensure it has digits too so we don't catch random dashes
    if ((s.includes("'") || s.includes('"') || s.includes('-')) && /\d/.test(s)) {
        // Feet: digits followed by ' or -
        const feetMatch = s.match(/^(\d+)['\-]/) || s.match(/(\d+)'/);
        // Inches: digits after ' or - or space, possibly followed by "
        const inchesMatch = s.match(/['\-\s](\d+(\.\d+)?)/) || s.match(/(\d+(\.\d+)?)?"/);

        let totalInches = 0;
        if (feetMatch) totalInches += parseInt(feetMatch[1]) * 12;
        if (inchesMatch && inchesMatch[1]) totalInches += parseFloat(inchesMatch[1]);

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
export function isBetter(a, b) {
    const pA = parseMark(a);
    const pB = parseMark(b);

    // If both invalid, neither is better
    if (!pA.valid && !pB.valid) return false;

    // If one is valid and other invalid, valid is better
    if (pA.valid && !pB.valid) return true;
    if (!pA.valid && pB.valid) return false;

    // Both valid: Compare values
    if (pA.isTime) {
        // Lower is better for time
        return pA.value < pB.value;
    } else {
        // Higher is better for distance
        return pA.value > pB.value;
    }
}
