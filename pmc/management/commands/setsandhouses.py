from django.core.management.base import BaseCommand
from decks.models import Set, House


class Command(BaseCommand):
    help = 'Creates initial set of sets and houses'

    def handle(self, *args, **options):
        self.stdout.write('Creating sets... ', ending='')
        self.make_sets()
        self.stdout.write(
            self.style.SUCCESS('OK')
        )

        self.stdout.write('Creating houses... ', ending='')
        self.make_houses()
        self.stdout.write(
            self.style.SUCCESS('OK')
        )

    def make_sets(self):
        Set.objects.get_or_create(id=341, defaults={
                                  'name': 'Call of the Archons', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217456/S01_CotA_qcqwnt.png'})
        Set.objects.get_or_create(id=435, defaults={
                                  'name': 'Age of Ascension', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217457/S02_AoA_mflcym.png'})
        Set.objects.get_or_create(id=452, defaults={
                                  'name': 'Worlds Collide', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217457/S03_WC_a1caus.png'})
        Set.objects.get_or_create(id=479, defaults={
                                  'name': 'Mass Mutation', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217457/S04_MM_lqkzfu.png'})
        Set.objects.get_or_create(id=496, defaults={
                                  'name': 'Dark Tidings', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217457/S05_DT_opxlsh.png'})
        Set.objects.get_or_create(id=600, defaults={
                                  'name': 'Winds of Exchange', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217458/S06_WoE_q9fpt9.png'})
        Set.objects.get_or_create(id=601, defaults={
                                  'name': 'Unchained 2022', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217456/N01_UC23_au4vbo.png'})
        Set.objects.get_or_create(id=609, defaults={
                                  'name': 'Vault Masters 2023', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217460/VM23_in21dn.png'})
        Set.objects.get_or_create(id=700, defaults={
                                  'name': 'Grim Reminders', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217458/S07_GR_zez1rs.png'})
        Set.objects.get_or_create(id=722, defaults={
                                  'name': 'Menagerie', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217456/N02_MN24_ksqyze.png'})
        Set.objects.get_or_create(id=737, defaults={
                                  'name': 'Vault Masters 2024', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217460/VM24_pjztcj.png'})
        Set.objects.get_or_create(id=800, defaults={
                                  'name': 'Æmber Skies', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217458/S08_AS_mgg8ww.png'})
        Set.objects.get_or_create(id=855, defaults={
                                  'name': 'Tokens of Change', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217456/L02_ToC_lujlto.png'})
        Set.objects.get_or_create(id=874, defaults={
                                  'name': 'More Mutation', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217456/L01_MORE_wcvzyv.png'})
        Set.objects.get_or_create(id=886, defaults={
                                  'name': 'Prophetic Visions', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217459/S09_PV_kmvhg6.png'})
        Set.objects.get_or_create(id=907, defaults={
                                  'name': 'Discovery', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1749217456/L03_DISC_imbvjy.png'})
        Set.objects.get_or_create(id=918, defaults={
                                  'name': 'Crucible Clash', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1750445067/L04_CC_vu6kyp.png'})

    def make_houses(self):
        House.objects.get_or_create(
            name='Brobnar', defaults={'mv_id': 'Brobnar', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425357/brobnar_ehqni1.png'})
        House.objects.get_or_create(name='Dis', defaults={
                                    'mv_id': 'Dis', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425357/dis_u1kdrl.png'})
        House.objects.get_or_create(
            name='Ekwidon', defaults={'mv_id': 'Ekwidon', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425357/ekwidon_yfgm80.png'})
        House.objects.get_or_create(
            name='Geistoid', defaults={'mv_id': 'Geistoid', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425357/geistoid_c0rggz.pnghttps://res.cloudinary.com/dig7eguxo/image/upload/v1751425357/geistoid_c0rggz.png'})
        House.objects.get_or_create(name='Logos', defaults={
                                    'mv_id': 'Logos', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425357/logos_w5vqm9.png'})
        House.objects.get_or_create(name='Mars', defaults={
                                    'mv_id': 'Mars', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425357/mars_bfcn75.png'})
        House.objects.get_or_create(name='Redemption', defaults={
                                    'mv_id': 'Redemption', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425358/redemption_updjsf.png'})
        House.objects.get_or_create(
            name='Sanctum', defaults={'mv_id': 'Sanctum', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425358/sanctum_lzowrj.png'})
        House.objects.get_or_create(
            name='Saurian', defaults={'mv_id': 'Saurian', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425358/saurian_dglfed.png'})
        House.objects.get_or_create(
            name='Shadows', defaults={'mv_id': 'Shadows', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425360/shadows_iw4fz3.png'})
        House.objects.get_or_create(
            name='Skyborn', defaults={'mv_id': 'Skyborn', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425360/skyborn_ossfu2.png'})
        House.objects.get_or_create(name='Star Alliance', defaults={
                                    'mv_id': 'Star Alliance', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425360/star-alliance_p8vlb6.png'})
        House.objects.get_or_create(name='Unfathomable', defaults={
                                    'mv_id': 'Unfathomable', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425360/unfathomable_bs11sv.png'})
        House.objects.get_or_create(
            name='Untamed', defaults={'mv_id': 'Untamed', 'src': 'https://res.cloudinary.com/dig7eguxo/image/upload/v1751425360/untamed_lyr8uu.png'})
