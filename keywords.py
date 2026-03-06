# ============================================================
# KEYWORDS COM PESOS (maior peso = maior frequência de sorteio)
#
# PESO 3 — Alta conversão comprovada (aparecem 3x mais na roleta)
# PESO 2 — Bom potencial
# PESO 1 — Nicho ou menor urgência
#
# Para adicionar: ("Nome da Keyword", peso)
# ============================================================

KEYWORDS_WEIGHTED = [
    # --- PESO 3 — Alta conversão comprovada ---

    # Skincare & Ativos
    ("Sérum Vitamina C Principia", 3),
    ("Sérum Niacinamida 10%", 3),
    ("Sérum Retinol Antienvelhecimento", 3),
    ("Protetor Solar Facial FPS 50", 3),
    ("Creme Facial Hidratante Noturno", 3),
    ("Kit Skincare Facial Completo", 3),

    # Maquiagem
    ("Blush Líquido Melu", 3),
    ("Blush Líquido Sheglam", 3),
    ("Lip Tint Bt", 3),
    ("Paleta Sombras Nude Océane", 3),
    ("Lip Gloss Plumping Volumoso", 3),
    ("Base Líquida Cobertura Alta", 3),

    # Cabelo
    ("Escova Secadora Mondial", 3),
    ("Chapinha Nano Titânio Bivolt", 3),
    ("Máscara Capilar Hidratação Profunda", 3),

    # Corpo & Bem-estar
    ("Rolo de Jade Rosto", 3),
    ("Massageador Facial Gua Sha", 3),
    ("Body Splash Wepink", 3),
    ("Suplemento Whey Feminino", 3),

    # Moda
    ("Legging Cintura Alta Levanta Bumbum", 3),
    ("Vestido Midi Fenda", 3),
    ("Vestido Slip Dress Cetim", 3),
    ("Conjunto Feminino Alfaiataria", 3),
    ("Conjunto Moletom Feminino Aesthetic", 3),
    ("Vestido Linho Midi Feminino", 3),
    ("Calça Jeans Wide Leg Feminina", 3),

    # Acessórios & Bolsas
    ("Tênis Dad Shoes Feminino", 3),
    ("Bolsa Shoulder Bag Feminina", 3),
    ("Nécessaire Grande Feminina Aesthetic", 3),

    # Casa & Decoração
    ("Copo Stanley Cores", 3),
    ("Garrafa Stanley Quente Frio", 3),
    ("Luminária Aesthetic Lua", 3),
    ("Difusor Varetas Ambiente Perfumado", 3),
    ("Tapete Felpudo Quarto Aesthetic", 3),

    # --- PESO 2 — Bom potencial ---

    # Skincare
    ("Sérum Retinol Facial", 2),
    ("Sérum Ácido Hialurônico", 2),
    ("Tônico Facial Glicólico", 2),
    ("Gel de Limpeza CeraVe", 2),
    ("Hidratante CeraVe Loção", 2),
    ("Óleo de Rosa Mosqueta", 2),
    ("Skincare Coreano Hidratante", 2),
    ("Máscara Facial Argila", 2),
    ("Patch Olheiras Colágeno", 2),

    # Maquiagem
    ("Pó Solto Boca Rosa", 2),
    ("Corretivo Fran by Lu", 2),
    ("Paleta de Sombras Océane", 2),
    ("Iluminador Líquido Facial", 2),
    ("Lip Gloss Volumoso", 2),

    # Cabelo
    ("Chapinha Bivolt Cerâmica", 2),
    ("Difusor Babyliss Cachos", 2),
    ("Finalizador Cachos Gelatina", 2),
    ("Máscara Capilar Kerastase", 2),
    ("Touca de Cetim Cabelo", 2),
    ("Tiara Pelúcia Aesthetic", 2),

    # Moda
    ("Conjunto Tricot Canelado", 2),
    ("Body Canelado Decote Quadrado", 2),
    ("Blazer Feminino Alfaiataria", 2),
    ("Calça Wide Leg Alfaiataria", 2),

    # Acessórios & Bolsas
    ("Bolsa Tote Aesthetic", 2),
    ("Bolsa Baguette Feminina", 2),
    ("Nécessaire Viagem Impermeável", 2),
    ("Kit Colar Feminino Dourado", 2),
    ("Tênis Feminino Plataforma Branco", 2),
    ("Chinelo Nuvem Feminino", 2),

    # Casa & Decoração
    ("Garrafa Térmica Pastel", 2),
    ("Umidificador Chama", 2),
    ("Difusor Óleos Essenciais", 2),
    ("Vela Aromática Decorativa", 2),
    ("Espelho Redondo Parede", 2),
    ("Cesta Rattan Organizadora", 2),
    ("Projetor Estrelas Quarto", 2),

    # Papelaria
    ("Agenda Planejador Feminino 2025", 2),
    ("Caderno Argolado Aesthetic", 2),

    # Saúde
    ("Suplemento Colágeno Verisol", 2),
    ("Vitamina Cabelo Unha Pele", 2),

    # --- PESO 1 — Nicho ou menor urgência ---

    # Skincare
    ("Cicaplast Baume B5", 1),
    ("Água Micelar Garnier", 1),
    ("Esfoliante Facial Suave", 1),
    ("Protetor Labial FPS", 1),
    ("Creme Contorno dos Olhos", 1),

    # Maquiagem
    ("Esponja Maquiagem Mari Saad", 1),
    ("Kit Pincel Sereia", 1),
    ("Delineador Olho de Gato", 1),
    ("Máscara Cílios Allday", 1),
    ("Batom Matte Longa Duração", 1),
    ("Setting Spray Fixador Maquiagem", 1),
    ("Primer Facial Poros", 1),

    # Cabelo
    ("Shampoo Lowpoo Cachos", 1),
    ("Condicionador Hidratante Salon Line", 1),
    ("Óleo Capilar Amend", 1),
    ("Protetor Térmico Capilar Spray", 1),
    ("Escova Cabelo Wet Brush", 1),

    # Corpo
    ("Creme Corporal Hidratante Intense", 1),
    ("Esfoliante Corporal Açúcar", 1),
    ("Óleo Corporal Iluminador", 1),
    ("Massageador Anticelulite Elétrico", 1),
    ("Espelho Led Maquiagem Mesa", 1),
    ("Cinta Modeladora Abdominal", 1),

    # Fitness & Lingerie
    ("Calcinha Sem Costura Kit", 1),
    ("Sutiã Adesivo Invisível", 1),
    ("Conjunto Fitness Sem Costura", 1),
    ("Top Fitness Regulável", 1),

    # Moda
    ("Vestido Longo Estampado Verão", 1),
    ("Cropped Ombro a Ombro Lastex", 1),
    ("Saia Midi Fenda Lateral", 1),
    ("Calça Pantalona Linho", 1),
    ("Vestido Babado Floral", 1),
    ("Camisa Feminina Linho Oversized", 1),

    # Acessórios & Bolsas
    ("Bolsa Transversal Feminina Pequena", 1),
    ("Mochila Feminina Casual", 1),
    ("Bolsa Palha Verão", 1),
    ("Relógio Feminino Minimalista", 1),
    ("Óculos de Sol Feminino Gatinho", 1),
    ("Brinco Argola Dourada Grande", 1),
    ("Papete Feminina Confortável", 1),
    ("Sandália Salto Bloco", 1),
    ("Mule Feminino Verniz", 1),

    # Casa & Organização
    ("Organizador de Acrílico Maquiagem", 1),
    ("Mop Giratório Flash Limp", 1),
    ("Robô Aspirador", 1),
    ("Despertador Digital Espelhado", 1),
    ("Potes Herméticos Mantimentos", 1),
    ("Forma Airfryer Silicone", 1),
    ("Tapete Super Absorvente Banheiro", 1),
    ("Cabides Veludo Antideslizante", 1),
    ("Mini Processador Elétrico Alho", 1),
    ("Jogo de Lençol 400 Fios", 1),
    ("Manta Sofá Tricot", 1),
    ("Quadro Decorativo Quarto Feminino", 1),
    ("Luz Led Quartos Aesthetic", 1),
    ("Kit Organizador Gaveta", 1),
    ("Porta Plantas Vaso Aesthetic", 1),

    # Papelaria
    ("Caneta Gel Colorida Kit", 1),
    ("Marca Páginas Aesthetic", 1),

    # Maternidade
    ("Bolsa Maternidade Grande", 1),
    ("Kit Higiene Bebê Aesthetic", 1),
    ("Almofada Amamentação", 1),

    # Pet
    ("Roupa Cachorro Aesthetic", 1),
    ("Cama Pet Pelúcia", 1),

    # Saúde
    ("Probiótico Feminino", 1),
]

# Expande a lista respeitando os pesos para uso com random.choice
KEYWORDS_POOL = [kw for kw, weight in KEYWORDS_WEIGHTED for _ in range(weight)]