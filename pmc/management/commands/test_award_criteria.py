from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pmc.models import AwardAssignmentService, Achievement, Trophy, AwardBase
from decks.models import House


class DummyAward:
    """Dummy award object for testing criteria"""
    def __init__(self, criteria, house=None):
        self.criteria = criteria
        self.house = house
        self.name = f"Test Award (Criteria {criteria})"
        self.pmc_id = f"test_{criteria}"
    
    def get_criteria_display(self):
        return dict(AwardBase.CriteriaTypeOptions.choices).get(self.criteria, f"Unknown ({self.criteria})")


class Command(BaseCommand):
    help = 'Test the get_user_criteria_value method for awards'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to test criteria for')
        parser.add_argument('award_type', type=str, choices=['achievement', 'trophy', 'criteria'], 
                          help='Type of award (achievement, trophy, or criteria)')
        parser.add_argument('award_id', type=str, help='Award ID (pmc_id) or criteria ID for testing')
        parser.add_argument('--house', type=str, help='House name for house-based criteria', required=False)

    def handle(self, *args, **options):
        username = options['username']
        award_type = options['award_type']
        award_id = options['award_id']
        house_name = options.get('house')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'User "{username}" does not exist')
            )
            return

        house = None
        if house_name:
            try:
                house = House.objects.get(name=house_name)
            except House.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'House "{house_name}" does not exist')
                )
                return

        if award_type == 'criteria':
            try:
                criteria_id = int(award_id)
                award = DummyAward(criteria_id, house)
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f'Criteria ID "{award_id}" must be a number')
                )
                return
        elif award_type == 'achievement':
            try:
                award = Achievement.objects.get(pmc_id=award_id)
            except Achievement.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Achievement with ID "{award_id}" does not exist')
                )
                return
        elif award_type == 'trophy':
            try:
                award = Trophy.objects.get(pmc_id=award_id)
            except Trophy.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Trophy with ID "{award_id}" does not exist')
                )
                return

        criteria_value = AwardAssignmentService.get_user_criteria_value(user, award)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'User: {user.username}\n'
                f'Award Type: {award_type.title()}\n'
                f'Award: {award.name} ({award.pmc_id})\n'
                f'Criteria: {award.get_criteria_display()}\n'
                f'House: {house.name if house else "N/A"}\n'
                f'Criteria Value: {criteria_value}'
            )
        )

        if award_type == 'trophy' and hasattr(award, 'criteria_value'):
            amount = criteria_value // award.criteria_value if award.criteria_value else 0
            self.stdout.write(
                self.style.WARNING(
                    f'Trophy Criteria Value: {award.criteria_value}\n'
                    f'Trophy Amount: {amount}'
                )
            )
        elif award_type == 'achievement' and hasattr(award, 'tiers'):
            tiers = award.tiers.all()
            for tier in tiers:
                if criteria_value >= tier.criteria_value:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Qualified for {tier.get_tier_display()} tier '
                            f'(requires {tier.criteria_value})'
                        )
                    )