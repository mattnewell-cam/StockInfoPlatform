from scripts.generate_AI_summaries import ask_gpt

ticker = 'VTY'
categories = ['description', 'special_sits', 'writeups']

with open('model_comparison.txt', 'w', encoding='utf-8') as f:
    for model in ['gpt-5-mini', 'gpt-5.2']:
        print(f'\n{"="*60}')
        print(f'{model}')
        print('='*60)
        f.write(f'{"="*60}\n')
        f.write(f'{model.upper()}\n')
        f.write(f'{"="*60}\n\n')

        for cat in categories:
            print(f'Generating {cat}...')
            result = ask_gpt(cat, ticker, model=model, effort='high')
            f.write(f'--- {cat} ---\n')
            f.write(str(result) + '\n\n')
            f.flush()

print('\nSaved to model_comparison.txt')
