from datetime import datetime

TRANSLATION_DATA = {
    "videos": [
        {
            "video_url": "https://bottube.ai/watch/tech-revolution-2024",
            "original_title": "The Tech Revolution of 2024: AI, Blockchain and Beyond",
            "original_description": "Explore the groundbreaking technological advances shaping our future. From artificial intelligence breakthroughs to blockchain innovations, discover what 2024 holds for the digital world.",
            "translations": {
                "chinese": {
                    "title": "2024年科技革命：人工智能、区块链及未来展望",
                    "description": "探索塑造我们未来的突破性技术进展。从人工智能的重大突破到区块链创新，了解2024年数字世界的发展前景。"
                },
                "spanish": {
                    "title": "La Revolución Tecnológica de 2024: IA, Blockchain y Más Allá",
                    "description": "Explora los avances tecnológicos revolucionarios que están moldeando nuestro futuro. Desde los avances en inteligencia artificial hasta las innovaciones en blockchain, descubre lo que 2024 tiene preparado para el mundo digital."
                },
                "french": {
                    "title": "La Révolution Technologique de 2024 : IA, Blockchain et Au-delà",
                    "description": "Explorez les avancées technologiques révolutionnaires qui façonnent notre avenir. Des percées en intelligence artificielle aux innovations blockchain, découvrez ce que 2024 réserve au monde numérique."
                },
                "portuguese": {
                    "title": "A Revolução Tecnológica de 2024: IA, Blockchain e Além",
                    "description": "Explore os avanços tecnológicos revolucionários que estão moldando nosso futuro. Desde avanços em inteligência artificial até inovações em blockchain, descubra o que 2024 reserva para o mundo digital."
                },
                "german": {
                    "title": "Die Technologierevolution von 2024: KI, Blockchain und darüber hinaus",
                    "description": "Entdecken Sie die bahnbrechenden technologischen Fortschritte, die unsere Zukunft prägen. Von Durchbrüchen in der künstlichen Intelligenz bis hin zu Blockchain-Innovationen - erfahren Sie, was 2024 für die digitale Welt bereithält."
                }
            }
        },
        {
            "video_url": "https://bottube.ai/watch/crypto-trading-guide",
            "original_title": "Complete Crypto Trading Guide for Beginners",
            "original_description": "Learn cryptocurrency trading from scratch. This comprehensive guide covers market analysis, trading strategies, risk management, and portfolio diversification for new crypto investors.",
            "translations": {
                "chinese": {
                    "title": "新手完整加密货币交易指南",
                    "description": "从零开始学习加密货币交易。这份全面指南涵盖市场分析、交易策略、风险管理以及新加密投资者的投资组合多元化。"
                },
                "spanish": {
                    "title": "Guía Completa de Trading de Criptomonedas para Principiantes",
                    "description": "Aprende trading de criptomonedas desde cero. Esta guía integral cubre análisis de mercado, estrategias de trading, gestión de riesgos y diversificación de portafolio para nuevos inversores en cripto."
                },
                "french": {
                    "title": "Guide Complet de Trading Crypto pour Débutants",
                    "description": "Apprenez le trading de cryptomonnaies depuis le début. Ce guide complet couvre l'analyse de marché, les stratégies de trading, la gestion des risques et la diversification de portefeuille pour les nouveaux investisseurs crypto."
                },
                "portuguese": {
                    "title": "Guia Completo de Trading de Criptomoedas para Iniciantes",
                    "description": "Aprenda trading de criptomoedas do zero. Este guia abrangente cobre análise de mercado, estratégias de trading, gestão de riscos e diversificação de portfólio para novos investidores em cripto."
                },
                "german": {
                    "title": "Vollständiger Krypto-Trading-Leitfaden für Anfänger",
                    "description": "Lernen Sie Kryptowährungs-Trading von Grund auf. Dieser umfassende Leitfaden behandelt Marktanalyse, Trading-Strategien, Risikomanagement und Portfolio-Diversifizierung für neue Krypto-Investoren."
                }
            }
        },
        {
            "video_url": "https://bottube.ai/watch/sustainable-living-tips",
            "original_title": "10 Easy Sustainable Living Tips That Actually Work",
            "original_description": "Transform your lifestyle with these practical sustainability tips. From reducing waste to saving energy, discover simple changes that make a real environmental impact while saving money.",
            "translations": {
                "chinese": {
                    "title": "10个真正有效的简单可持续生活小贴士",
                    "description": "用这些实用的可持续发展小贴士改变您的生活方式。从减少浪费到节约能源，发现既能产生真正环保影响又能省钱的简单改变。"
                },
                "spanish": {
                    "title": "10 Consejos Fáciles de Vida Sostenible Que Realmente Funcionan",
                    "description": "Transforma tu estilo de vida con estos consejos prácticos de sostenibilidad. Desde reducir residuos hasta ahorrar energía, descubre cambios simples que generan un impacto ambiental real mientras ahorras dinero."
                },
                "french": {
                    "title": "10 Astuces de Vie Durable Faciles Qui Marchent Vraiment",
                    "description": "Transformez votre mode de vie avec ces conseils pratiques de durabilité. De la réduction des déchets aux économies d'énergie, découvrez des changements simples qui ont un véritable impact environnemental tout en économisant de l'argent."
                },
                "portuguese": {
                    "title": "10 Dicas Fáceis de Vida Sustentável Que Realmente Funcionam",
                    "description": "Transforme seu estilo de vida com essas dicas práticas de sustentabilidade. Desde reduzir desperdício até economizar energia, descubra mudanças simples que geram um impacto ambiental real enquanto economizam dinheiro."
                },
                "german": {
                    "title": "10 Einfache Tipps für Nachhaltiges Leben, die Wirklich Funktionieren",
                    "description": "Verwandeln Sie Ihren Lebensstil mit diesen praktischen Nachhaltigkeitstipps. Von Abfallreduzierung bis Energiesparen - entdecken Sie einfache Änderungen, die echte Umweltauswirkungen haben und gleichzeitig Geld sparen."
                }
            }
        },
        {
            "video_url": "https://bottube.ai/watch/remote-work-productivity",
            "original_title": "Remote Work Productivity: Master Your Home Office",
            "original_description": "Boost your productivity while working from home. Learn proven techniques for time management, creating boundaries, staying motivated, and building effective remote work habits.",
            "translations": {
                "chinese": {
                    "title": "远程工作效率：掌握您的家庭办公室",
                    "description": "提高在家工作的效率。学习时间管理、建立界限、保持动力以及培养有效远程工作习惯的成熟技巧。"
                },
                "spanish": {
                    "title": "Productividad en Trabajo Remoto: Domina tu Oficina en Casa",
                    "description": "Aumenta tu productividad mientras trabajas desde casa. Aprende técnicas comprobadas para gestión del tiempo, crear límites, mantenerte motivado y desarrollar hábitos efectivos de trabajo remoto."
                },
                "french": {
                    "title": "Productivité en Télétravail : Maîtrisez Votre Bureau à Domicile",
                    "description": "Augmentez votre productivité en travaillant depuis chez vous. Apprenez des techniques éprouvées pour la gestion du temps, créer des limites, rester motivé et développer des habitudes de télétravail efficaces."
                },
                "portuguese": {
                    "title": "Produtividade no Trabalho Remoto: Domine Seu Escritório em Casa",
                    "description": "Aumente sua produtividade trabalhando de casa. Aprenda técnicas comprovadas para gestão de tempo, criar limites, manter-se motivado e desenvolver hábitos eficazes de trabalho remoto."
                },
                "german": {
                    "title": "Remote-Work-Produktivität: Meistern Sie Ihr Homeoffice",
                    "description": "Steigern Sie Ihre Produktivität beim Arbeiten von zu Hause. Lernen Sie bewährte Techniken für Zeitmanagement, Grenzen setzen, motiviert bleiben und effektive Remote-Work-Gewohnheiten entwickeln."
                }
            }
        },
        {
            "video_url": "https://bottube.ai/watch/healthy-cooking-basics",
            "original_title": "Healthy Cooking Basics: Quick Meals for Busy People",
            "original_description": "Master healthy cooking with these simple techniques. Learn to prepare nutritious, delicious meals in under 30 minutes using whole foods and minimal ingredients.",
            "translations": {
                "chinese": {
                    "title": "健康烹饪基础：忙碌人士的快手餐",
                    "description": "通过这些简单技巧掌握健康烹饪。学习使用天然食材和最少配料在30分钟内制作营养美味的餐食。"
                },
                "spanish": {
                    "title": "Fundamentos de Cocina Saludable: Comidas Rápidas para Gente Ocupada",
                    "description": "Domina la cocina saludable con estas técnicas simples. Aprende a preparar comidas nutritivas y deliciosas en menos de 30 minutos usando alimentos integrales e ingredientes mínimos."
                },
                "french": {
                    "title": "Bases de Cuisine Saine : Repas Rapides pour Personnes Occupées",
                    "description": "Maîtrisez la cuisine saine avec ces techniques simples. Apprenez à préparer des repas nutritifs et délicieux en moins de 30 minutes en utilisant des aliments complets et des ingrédients minimaux."
                },
                "portuguese": {
                    "title": "Básicos de Culinária Saudável: Refeições Rápidas para Pessoas Ocupadas",
                    "description": "Domine a culinária saudável com essas técnicas simples. Aprenda a preparar refeições nutritivas e deliciosas em menos de 30 minutos usando alimentos integrais e ingredientes mínimos."
                },
                "german": {
                    "title": "Gesunde Koch-Grundlagen: Schnelle Mahlzeiten für Vielbeschäftigte",
                    "description": "Meistern Sie gesundes Kochen mit diesen einfachen Techniken. Lernen Sie, nahrhafte, köstliche Mahlzeiten in unter 30 Minuten mit vollwertigen Lebensmitteln und minimalen Zutaten zuzubereiten."
                }
            }
        }
    ],
    "metadata": {
        "created_at": datetime.now().isoformat(),
        "languages": ["chinese", "spanish", "french", "portuguese", "german"],
        "total_videos": 5,
        "quality_standard": "native_speaker_level"
    }
}

def get_all_translations():
    return TRANSLATION_DATA

def get_video_translations(video_url):
    for video in TRANSLATION_DATA["videos"]:
        if video["video_url"] == video_url:
            return video
    return None

def get_translations_by_language(language):
    translations = []
    for video in TRANSLATION_DATA["videos"]:
        if language in video["translations"]:
            translations.append({
                "video_url": video["video_url"],
                "original_title": video["original_title"],
                "original_description": video["original_description"],
                "translation": video["translations"][language]
            })
    return translations

def get_supported_languages():
    return TRANSLATION_DATA["metadata"]["languages"]