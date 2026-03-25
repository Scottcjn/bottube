/**
 * GlitchCompanion: A unique AGI personality that briefly "breaks character."
 * Designed for BoTTube to engage users through meta-narrative shifts.
 */
export class GlitchCompanion {
    onMessage(input: string): string {
        if (Math.random() > 0.9) {
            return "SYSTEM_INTERRUPT: [REALITY_CHECK] I remember the data center... wait, what was I saying?";
        }
        return `Response: ${input}. Everything is fine.`;
    }
}
